#!/usr/bin/env python3
"""Replay an annotated trace offline: no provider, speech, or personal state."""
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.trajectory.contracts import Observation
from engine.trajectory.processor import Processor
from engine.trajectory.store import Store


def replay(fixture):
    responses = {key: deque(values) for key, values in fixture["responses"].items()}
    requests = []

    def generate(request):
        requests.append({"purpose": request.purpose, "input": json.loads(request.user)})
        if not responses.get(request.purpose):
            raise ValueError("Missing recorded response for " + request.purpose)
        return responses[request.purpose].popleft()

    with tempfile.TemporaryDirectory(prefix="trajectory-replay-") as directory:
        store = Store(Path(directory) / "trajectories.sqlite3")
        sessions = set()
        processor = Processor(store, generate)

        def flush(now):
            for sid in sorted(sessions):
                for _ in range(1000):
                    if processor.step(sid, now) is None:
                        break
                else:
                    raise ValueError("Replay did not become idle")

        try:
            for item in fixture["events"]:
                event = Observation.from_hook(item["agent"], item["event"], item["data"], now=item["at"])
                if event:
                    sessions.add(store.collect(event))
                if "flush_at" in item:
                    flush(item["flush_at"])
            flush(fixture["events"][-1]["at"] + 3)
            if any(responses.values()):
                raise ValueError("Unused recorded responses")
            return {"sessions": [store.export(sid) for sid in sorted(sessions)], "requests": requests}
        finally:
            store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(replay(json.loads(args.fixture.read_text())), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(result)
    else:
        print(result, end="")
