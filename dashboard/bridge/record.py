"""Recording and replaying runs.

A recorded run is the project's test fixture and its calibration data. It is how the
city-approach distance stops being a guess, and how the dashboard gets developed on a
machine with no game on it.

Format is JSON Lines: one frame per line, so a recording streams, truncates safely and
diffs readably.
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from pathlib import Path

from .model import Damage, Job, Switches, Telemetry


def to_dict(t: Telemetry) -> dict:
    out = {}
    for f in fields(t):
        v = getattr(t, f.name)
        out[f.name] = vars(v).copy() if is_dataclass(v) else v
    return out


def from_dict(d: dict) -> Telemetry:
    t = Telemetry()
    nested = {"job": Job, "damage": Damage, "switches": Switches}
    for f in fields(t):
        if f.name not in d:
            continue
        if f.name in nested:
            obj = nested[f.name]()
            for k, v in (d[f.name] or {}).items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            setattr(t, f.name, obj)
        else:
            setattr(t, f.name, d[f.name])
    return t


class Recorder:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")
        self.count = 0

    def write(self, t: Telemetry) -> None:
        self._fh.write(json.dumps(to_dict(t), separators=(",", ":")) + "\n")
        self.count += 1

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.flush()
            self._fh.close()

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def load(path: str | Path) -> list[Telemetry]:
    frames: list[Telemetry] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                frames.append(from_dict(json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from None
    return frames
