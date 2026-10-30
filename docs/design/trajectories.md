# Persistent session and interaction trajectories

This feature implements [issue #23](https://github.com/zorhay/code-gossip/issues/23): commentary that follows progress toward the task throughout a session. The mechanism is progressive summarization. Trajectories are persistent records, even when narration stays silent.

## Domain and relationships

There are exactly two trajectory levels:

```text
Session
├── Session trajectory (one)
│   └── Ordered session records (one per summarized interaction)
└── Interactions (many)
    ├── Interaction trajectory (one)
    │   └── Ordered interaction records (one per summarized batch)
    └── Batches (many)
        ├── Observed events (many)
        └── Narration decision (at most one)

Batch of events ──summarize──► Interaction trajectory record
Entire interaction trajectory ──summarize──► Session trajectory record
Session trajectory + active interaction trajectory + speech history ──► Narration
```

An **interaction** is a user request and its associated agent work/response. A **batch** is a bounded group of observations within that interaction. An **interaction trajectory** preserves the detailed progression toward that interaction's goal. A **session trajectory** preserves the broader progression across interactions. Its records remain linked to their source interaction trajectories.

The original session request and every interaction request are stored separately from generated text. Each batch becomes one factual summary, including routine work. Silence is decided afterward. An interaction ending is not evidence that the overall task succeeded.

## Persistence contract

[`Store`](../../code-gossip/engine/trajectory/store.py) owns `paths.STATE / "trajectories.sqlite3"`. SQLite foreign keys and short transactions protect writes from concurrent hooks. The database is private to the runtime, uses WAL, and has no dependency on Soundbar.

| Table | One row represents | Identity / relationship |
|---|---|---|
| `sessions` | One native conversation | Unique agent + native session ID; original task and last activity |
| `interactions` | One user interaction | Session FK; native turn ID when supplied; ordered within session; request and ending status |
| `session_trajectories` | The persistent session trajectory | Session ID is its primary key |
| `interaction_trajectories` | The persistent interaction trajectory | Interaction ID is its primary key |
| `events` | One received observation | Session FK; nullable interaction/batch FKs; native event/call IDs, arrival time, original payload and bounded model evidence |
| `batches` | One group of events | Interaction FK; ordered within interaction; open/closed, limits, attempts and error state |
| `interaction_records` | One batch summary | Batch ID is its primary key; interaction trajectory FK |
| `session_records` | One interaction summary | Source interaction trajectory ID is its primary key; session trajectory FK; processed-through batch |
| `narrations` | One consideration of new trajectory material | Unique batch FK; considered coverage, text or silence, delivery status |
| `tool_links` | A source call/process/subagent association | Scoped to session; identifies the owning interaction |

Unique source keys make retries idempotent. Storage methods derive the owning trajectory from the batch/interaction instead of accepting arbitrary relationships. Original events are not overwritten by generated commentary.

Trajectory root rows may hold a **derived context cache** and its coverage position. These are bounded prompt views, not replacements for the ordered records or another trajectory level. No snapshot revisions are stored.

## Module contracts

| Module | Input → output | Dependencies excluded |
|---|---|---|
| [Agent adapters](../../code-gossip/hooks/) | Native hook → observation; independently, optional sound cue | Summary prompts, speech scheduling |
| [Contracts](../../code-gossip/engine/trajectory/contracts.py) | Native identity/payload → `Observation`; request/result data classes | Configuration, SQL, providers, audio |
| [Store](../../code-gossip/engine/trajectory/store.py) | Evidence and summaries → durable domain records | LLMs, speech, Soundbar |
| [Builders](../../code-gossip/engine/trajectory/builders.py) | Batch → `BatchSummary`; interaction trajectory → `InteractionSummary` | SQL, settings, audio |
| [Processor](../../code-gossip/engine/trajectory/processor.py) | Repository + injected text generator → ordered trajectory updates and narration decisions | Concrete provider or speech engine |
| [Commentary](../../code-gossip/engine/commentary.py) | Both trajectories + prior delivered speech → silence or 1–2 sentences | Collection and trajectory mutation |
| [LLM transport](../../code-gossip/engine/llm.py) | `TextRequest` → text | Trajectories, settings files, speech |
| [Speech](../../code-gossip/engine/speech.py) | Text + engine/voice/volume → delivery success | LLMs, collection, trajectories |
| [Runtime](../../code-gossip/engine/trajectory/runtime.py) | Settings + concrete implementations → ingestion, workers, delivery | Soundbar process availability |

The runtime is the composition root. Builders receive a `generate(TextRequest)` callable; the processor receives a repository. Provider-specific calls and SQL stay behind those boundaries. Styles affect final commentary, not factual summaries. Speech runs in a separate process, so playing or failing audio cannot block trajectory construction.

`narrate.py` retains isolated preview and speech/check CLI entrypoints. Live hooks no longer invoke its single-event narrator through `play.sh`.

## Collection and interaction boundaries

Adapters submit observations before sound normalization or filtering. Codex quiet tools and successful non-shell results can therefore contribute evidence. Claude uses an adapter with generic pre/post tool registrations. Cursor observes prompts, generic tool results and agent responses in addition to existing sound events.

Native turn IDs are preferred: Codex `turn_id`, Claude `prompt_id` when available, and Cursor `generation_id`. Tool-call/process IDs correlate delayed output with its original interaction. Observed subagent-start identities associate subsequent child evidence with the parent interaction. Without native identifiers, prompt/stop boundaries and the active interaction are the fallback; late results without correlation identifiers cannot be attributed with the same certainty.

A new prompt can supersede an unfinished interaction. Stops, failures, interruptions, and session endings retain their distinct status. An activity pause closes a batch, not an interaction. Events lacking a known interaction are retained unassigned. Events without a conversation identity are skipped; working directories are never substituted for session IDs.

Hooks remain observational: no permission/trust changes and no output to the agent. Failures in collection cannot disable the independent effects/fixed-phrase path. Code Gossip's own Claude CLI calls carry `CODE_GOSSIP_INTERNAL=1`; adapters ignore their hooks to prevent recursive narration.

Hook schemas were checked against the [Claude reference](https://code.claude.com/docs/en/hooks) and [Cursor reference](https://cursor.com/docs/hooks). Coverage still depends on the host: unavailable, redacted, or truncated results cannot become complete evidence.

## Building the two trajectories

**Batch → interaction record.** Close a batch after two seconds of quiet, fifteen seconds maximum age, twenty events, or twenty-four KiB of selected evidence. Permission and terminal events close it promptly. The builder receives the original task, interaction request, prior session context, preceding interaction context, and new evidence. It returns one concise factual summary. Empty, oversized, or silent summary responses are rejected; the batch remains pending.

**Interaction trajectory → session record.** Flush the terminal batch, finish its interaction summaries, then compress the interaction into one session record. Commit that record before processing a later interaction, so its outcome is available to subsequent work. A delayed result can extend the original interaction trajectory; its session record is then rebuilt in place. The unique source interaction key prevents duplicate session records. Unknown endings remain unrolled until an explicit boundary arrives.

Long trajectories compact older summaries into a bounded context cache while keeping recent records in the prompt. Original records remain stored. Cache updates are discarded if new observations arrive during compression. Changes to earlier source material invalidate dependent session context.

One process lock serializes work for each session. Collection uses separate short SQLite transactions and continues during provider calls. A summary and its durable row commit together; records themselves are the processing checkpoints. No database transaction remains open across a model call. A worker owns the quiet timer, so the last batch is processed without waiting for another hook. Work survives worker restarts; provider failures get three attempts per worker run and remain pending for a later wakeup.

## Narration and delivery

Narration reads earlier session records, the active interaction trajectory, the original/current requests, and recently delivered lines. It can remain silent. Queued material can be superseded by newer work; speech delivery rechecks the current interaction and batch before playback.

Delivery has a separate global process lock and records `pending`, `playing`, `completed`, `failed`, `muted`, `superseded`, or `uncertain`. A crashed speaker leaves uncertain delivery rather than triggering an automatic replay. Only acknowledged completed speech enters delivered history. Existing voice spacing and approval-audio preferences remain effective.

When AI commentary is active, both trajectory builders run even if audio is temporarily muted or suppressed. Switching to another mode stops new model work at a checkpoint. Effects and fixed phrases do not need trajectories or an LLM. Preview generation uses synthetic context and never writes live trajectories. Installation/update/removal stops only identity-checked workers belonging to that runtime.

LLM work is per batch and per interaction, not per hook: one interaction-summary call per batch, one session-summary call per ended interaction, plus narration when there is unconsidered material. Older-context compression may add calls. The former optional deep-context setting is removed; no old session-memory files are migrated.

## Retention and inspection

Original payloads are limited to sixty-four KiB per event with explicit truncation metadata; model evidence is a bounded projection. Worker maintenance limits retained raw/evidence text to thirty-two MiB per session, marking evicted evidence while keeping trajectory records. Inactive sessions and dependent records expire after seven days. These are local runtime files, not release content.

Replay a representative trace without a provider, speech, or personal settings:

```bash
python3 -B code-gossip/engine/trajectory/replay.py tests/fixtures/trajectory-session.json --output /tmp/trajectory-replay.json
```

The fixture's model responses are illustrative recorded text. It tests ordering and contracts, not live-model semantic quality. Its two interactions produce four interaction records and two session records, with silent work, a reproduced failure, and recovery while preserving a follow-up constraint.

Inspect a local session using its internal database ID:

```bash
python3 -B code-gossip/engine/trajectory/runtime.py inspect ~/.code-gossip 1
```

[`tests/test_trajectories.py`](../../tests/test_trajectories.py) exercises the two levels, native/fallback identities, concurrent collection, late results, child provenance, retries, idle flushing, compaction, retention, speech history, and self-observation prevention. Installer, UI, and release tests cover registration and distribution. Live-provider summary quality still requires listening/review with real sessions; automated tests use injected responses.
