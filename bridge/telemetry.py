"""Secret-free worker telemetry; never store cloud response bodies or URLs."""
import json
import os
from pathlib import Path
import time

state = {"phase": "starting", "sessions": 0, "events": []}


def update(**values):
    state.update(values)
    state["updated"] = time.time()
    target = os.getenv("BRIDGE_TELEMETRY")
    if target:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(state), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            pass  # Monitoring must never interrupt video.


def event(message, **values):
    state["events"] = (state["events"] + [{"time": time.time(), "message": message}])[-40:]
    update(**values)
