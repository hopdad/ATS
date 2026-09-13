"""Cab Deck bridge CLI.

    python -m bridge simulate               watch derived telemetry with no game running
    python -m bridge record -o run.jsonl    capture a run for replay and calibration
    python -m bridge replay run.jsonl       play a recording back through the pipeline
    python -m bridge probe                  what the real source still needs
"""

from __future__ import annotations

import argparse
import sys
import time

from . import derive, record
from .derive import AlertTracker, Config
from .scale import ScaleEstimator
from .sources import ReplaySource, SimulatedSource


def _fmt_minutes(m: float | None) -> str:
    if m is None:
        return "  --  "
    if m == float("inf"):
        return "  inf "
    h, mm = int(m // 60), int(round(m % 60))
    return f"{h}h{mm:02d}" if h else f"{mm:4d}m"


def _line(f: dict) -> str:
    limit = f["speed_limit"]
    flag = "!" if f["over_limit"] else " "
    bites = f["bites_first"]
    pay = f["pay_per_real_hour"]
    alerts = ",".join(a["code"] for a in f["alerts"]) or "-"
    return (
        f"{f['speed']:5.1f}{flag}/{limit if limit is None else round(limit):>3} mph"
        f" | scale {0 if f['scale'] is None else f['scale']:>4.1f}x"
        f" | {f['distance_remaining']:6.1f} mi"
        f" | real {_fmt_minutes(f['real_minutes_left'])}"
        f" | {'$%7.0f/h' % pay if pay else '      --   '}"
        f" | first: {bites['key'] if bites else '-':<8}"
        f" {_fmt_minutes(bites['real_minutes'] if bites else None)}"
        f" | {alerts}"
    )


def _pipeline(source, hz: float, seconds: float | None, cfg: Config, on_frame=None) -> int:
    est, tracker = ScaleEstimator(), AlertTracker()
    period, started, n = 1.0 / hz, time.monotonic(), 0
    while True:
        t = source.read()
        if t is None:
            break
        if not t.received_at:
            t.received_at = time.monotonic()
        est.update(t.received_at, t.game_time_min)
        tracker.update(t)
        scale = est.effective(t.local_scale or None)
        est.note(scale, t.speed_ms)
        f = derive.frame(t, scale, cfg, tracker, est.cruise_scale, est.highway_speed_ms)
        n += 1
        if on_frame:
            on_frame(t, f)
        if seconds is not None and time.monotonic() - started >= seconds:
            break
        time.sleep(period)
    return n


def cmd_simulate(args) -> int:
    cfg = Config(units=args.units)
    src = SimulatedSource(speed_factor=args.speed)
    every = max(1, int(args.hz / 4))
    state = {"i": 0}

    def show(_t, f):
        state["i"] += 1
        if state["i"] % every == 0:
            print(_line(f))

    print("simulated run — no game required.  speed x%g\n" % args.speed)
    n = _pipeline(src, args.hz, args.seconds, cfg, show)
    print(f"\n{n} frames")
    return 0


def cmd_record(args) -> int:
    cfg = Config(units=args.units)
    src = SimulatedSource(speed_factor=args.speed)
    with record.Recorder(args.out) as rec:
        n = _pipeline(src, args.hz, args.seconds, cfg, lambda t, f: rec.write(t))
        print(f"wrote {rec.count} frames to {args.out}")
    return 0 if n else 1


def cmd_replay(args) -> int:
    cfg = Config(units=args.units)
    frames = record.load(args.path)
    print(f"{len(frames)} frames from {args.path}\n")
    n = _pipeline(ReplaySource(frames), args.hz, None, cfg, lambda t, f: print(_line(f)))
    print(f"\n{n} frames")
    return 0


def cmd_probe(args) -> int:
    print(
        "The real source needs the plugin's struct layout, which is not safe to guess:\n"
        "a wrong offset decodes to a plausible number rather than an error.\n\n"
        "On the gaming PC:\n"
        "  1. install scs-sdk-plugin into the game's bin/win_x64/plugins\n"
        "  2. fetch its scs-telemetry-common.hpp\n"
        "  3. python -m bridge layout scs-telemetry-common.hpp -o layouts/rencloud.json\n"
        "  4. python -m bridge probe --layout layouts/rencloud.json\n\n"
        "Until then: `simulate` and `replay` exercise the whole pipeline without it."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    # Shared flags go on a parent parser so they work on either side of the
    # subcommand -- `bridge --hz 30 simulate` and `bridge simulate --hz 30` both read
    # the way people expect.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--units", choices=("us", "metric"), default="us")
    common.add_argument("--hz", type=float, default=20.0)

    p = argparse.ArgumentParser(prog="bridge", description=__doc__, parents=[common],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate", parents=[common], help="run the pipeline against a simulated truck")
    s.add_argument("--seconds", type=float, default=20.0)
    s.add_argument("--speed", type=float, default=4.0, help="run the sim faster than real time")
    s.set_defaults(fn=cmd_simulate)

    r = sub.add_parser("record", parents=[common], help="capture frames to a JSONL file")
    r.add_argument("-o", "--out", required=True)
    r.add_argument("--seconds", type=float, default=20.0)
    r.add_argument("--speed", type=float, default=4.0)
    r.set_defaults(fn=cmd_record)

    rp = sub.add_parser("replay", parents=[common], help="play a recording back through the pipeline")
    rp.add_argument("path")
    rp.set_defaults(fn=cmd_replay)

    pr = sub.add_parser("probe", parents=[common], help="what the real telemetry source still needs")
    pr.add_argument("--layout")
    pr.set_defaults(fn=cmd_probe)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
