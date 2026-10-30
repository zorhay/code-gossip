# Persistent trajectories

## Intention

[Issue #23](https://github.com/zorhay/code-gossip/issues/23): make commentary explain progress toward the user's goal throughout a session. Summarize large volumes of operations, code, and logs into one or two useful spoken sentences when something meaningful changes.

## Data and relationships

An **interaction** is one user request and its associated agent work. A **trajectory** is a persistent, ordered account of how that work progresses toward the goal.

```text
Session
├── Session trajectory (one)
│   └── Records (one summary per interaction)
└── Interactions (many)
    ├── Interaction trajectory (one)
    │   └── Records (one summary per batch)
    └── Batches (many)
        └── Observed events (many)
```

Each summary links to its source batch or interaction. The original task and subsequent user requests remain stored separately from generated summaries.

## Summarization flow

1. **Collect:** group observed events into batches within their interaction.
2. **Build the interaction trajectory:** summarize each batch into one new record, using the task, current request, and preceding trajectories as context.
3. **Build the session trajectory:** when an interaction ends, summarize its entire trajectory into one session record. Late evidence updates that interaction's summary.
4. **Narrate:** read both trajectories and previously spoken lines; produce one or two sentences about meaningful progress, or stay silent.

Quiet work still contributes to both trajectories. Summaries distinguish attempted actions from confirmed results; an interaction ending does not prove the task is complete.

## Module boundaries

| Module | Responsibility |
|---|---|
| Agent adapters | Collect observations independently of sound filtering |
| Store | Persist events, relationships, trajectories, and speech history |
| Trajectory builders | Summarize batches and interactions through an injected text generator |
| Commentary | Read trajectories and decide what merits speech |
| LLM transport | Execute text-generation requests |
| Speech | Deliver text and report whether playback succeeded |

The processor coordinates trajectory updates; the runtime supplies storage, provider, and speech implementations. Builders contain no SQL or audio logic. Narration consumes trajectories without owning their construction.

See [Architecture](../../ARCHITECTURE.md#narration-and-speech) for runtime details.
