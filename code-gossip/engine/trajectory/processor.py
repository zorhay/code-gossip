"""Application coordination; repository and text generation are injected."""
from . import builders
from engine.commentary import compose


class Processor:
    def __init__(self, store, generate, style="", narrate=True):
        self.store, self.generate, self.style, self.narrate = store, generate, style, narrate

    def context(self, scope, owner, before=None):
        generation = self.store.generation(self.store.trajectory_session(scope, owner))
        view = self.store.trajectory(scope, owner, before=before)
        compacted, update = builders.compact(view, self.generate)
        if update:
            self.store.save_context(scope, owner, *update, expected_generation=generation)
        return compacted

    def step(self, sid, now):
        """Make at most one durable trajectory change; never call audio."""
        self.store.seal_due(sid, now)
        session = self.store.session(sid)
        batch = self.store.next_batch(sid)
        rollup = self.store.next_rollup(sid)
        if rollup and (not batch or rollup["ordinal"] <= batch["interaction_order"]):
            trajectory = self.context("interaction", rollup["id"])
            previous = self.context("session", sid, before=rollup["ordinal"])
            summary = builders.session(rollup, trajectory, previous, session["original_task"], self.generate)
            self.store.commit_rollup(summary, now)
            return "session"
        if batch and batch["closed"]:
            previous = self.context("session", sid, before=batch["interaction_order"])
            trajectory = self.context("interaction", batch["interaction_id"])
            try:
                summary = builders.interaction(batch, self.store.batch_events(batch["id"]), previous,
                                               trajectory, session["original_task"], self.generate)
                self.store.commit_batch(summary, now)
            except Exception:
                self.store.batch_failed(batch["id"])
                raise
            return "batch"
        if self.narrate:
            candidate = self.store.narration_candidate(sid)
            if candidate:
                previous = self.context("session", sid, before=candidate["interaction_order"])
                trajectory = self.context("interaction", candidate["interaction_id"])
                text = compose(session["original_task"], candidate["request"], previous, trajectory,
                               self.store.delivered(sid), self.style, self.generate)
                if text and self.store.already_delivered(sid, text):
                    text = ""
                self.store.record_narration(candidate["id"], text, "pending" if text else "silent", now)
                return "narration"
        return None
