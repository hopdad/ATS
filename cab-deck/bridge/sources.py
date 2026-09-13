"""Where frames come from.

Three sources behind one interface, which is what lets the dashboard be built and
tested with no game installed:

  SimulatedSource      a procedural run. No game, no plugin, no Windows.
  ReplaySource         a recorded run played back. Deterministic, so it makes tests.
  SharedMemorySource   the real thing, reading the plugin's memory-mapped file.

The first two are complete. The third needs the plugin's struct layout, which is not
something to guess -- see bridge/layout.py.
"""

from __future__ import annotations

import math
import time
from typing import Iterator, Protocol

from .model import Telemetry, MS_PER_MPH, M_PER_MILE


class Source(Protocol):
    def read(self) -> Telemetry | None: ...
    def close(self) -> None: ...


class SimulatedSource:
    """A Bakersfield to Barstow run, including the city approach where time slows down.

    Scripted rather than random so that what it exercises is predictable: a speed-limit
    drop, a stretch at city scale, a falling air pressure alert, and fuel burn.
    """

    def __init__(self, speed_factor: float = 1.0, start: float | None = None) -> None:
        self.speed_factor = speed_factor
        self._t0 = start if start is not None else time.monotonic()
        self._last = self._t0
        self.distance_m = 128 * M_PER_MILE
        self.fuel_l = 258.0
        self.game_min = 14 * 60 + 36
        self._speed = 52 * MS_PER_MPH

    def _phase(self, elapsed: float) -> tuple[float, float, float]:
        """(speed limit m/s, target speed m/s, local scale) for this point in the run."""
        if elapsed < 30:
            return 55 * MS_PER_MPH, 54 * MS_PER_MPH, 20.0
        if elapsed < 60:
            return 45 * MS_PER_MPH, 51 * MS_PER_MPH, 20.0     # over the limit on purpose
        if elapsed < 95:
            return 35 * MS_PER_MPH, 32 * MS_PER_MPH, 3.0      # town: time slows right down
        return 65 * MS_PER_MPH, 63 * MS_PER_MPH, 20.0

    def read(self) -> Telemetry:
        now = time.monotonic()
        dt = (now - self._last) * self.speed_factor
        self._last = now
        elapsed = (now - self._t0) * self.speed_factor

        limit, target, scale = self._phase(elapsed)
        self._speed += (target - self._speed) * min(1.0, dt * 0.6)

        travelled = self._speed * dt * scale          # game distance advances with game time
        self.distance_m = max(0.0, self.distance_m - travelled)
        self.game_min += dt / 60.0 * scale
        self.fuel_l = max(0.0, self.fuel_l - travelled / 1000.0 * 0.38)

        t = Telemetry()
        t.speed_ms = self._speed
        t.speed_limit_ms = limit
        t.rpm = 900 + (self._speed / (70 * MS_PER_MPH)) * 1150 + math.sin(elapsed / 2) * 40
        t.gear = 1 if self._speed < 2 else min(12, 8 + int(self._speed / (18 * MS_PER_MPH)))
        t.fuel_l = self.fuel_l
        t.fuel_capacity_l = 568.0
        t.fuel_avg_consumption_lpkm = 0.38
        t.air_pressure_psi = 88 - (elapsed - 40) * 0.25 if 40 < elapsed < 75 else 118.0
        t.oil_pressure_psi = 45.0
        t.oil_temp_c = 92.0
        t.water_temp_c = 88.0
        t.battery_v = 27.4
        t.game_time_min = self.game_min
        t.local_scale = scale
        t.next_rest_min = max(0.0, 72 * 20 - (self.game_min - (14 * 60 + 36)))

        t.job.on_job = True
        t.job.source_city, t.job.source_company = "Bakersfield", "Gallogly Steel"
        t.job.dest_city, t.job.dest_company = "Barstow", "Wallbert DC"
        t.job.cargo, t.job.cargo_mass_kg = "Machinery", 19096.0
        t.job.income = 4180.0
        t.job.remaining_distance_m = self.distance_m
        t.job.delivery_deadline_min = (14 * 60 + 36) + 260 * 20

        t.damage.truck, t.damage.trailer = 0.02, 0.07
        t.switches.low_beam = True
        t.switches.parking_brake = False
        t.switches.engine_running = True
        t.switches.trailer_attached = True
        t.switches.retarder_level = 0
        t.received_at = now
        return t

    def close(self) -> None:
        pass


class ReplaySource:
    """Plays a recorded run back. Deterministic, which is what makes it useful in tests."""

    def __init__(self, frames: list[Telemetry], loop: bool = False) -> None:
        if not frames:
            raise ValueError("replay needs at least one frame")
        self.frames = frames
        self.loop = loop
        self._i = 0

    def read(self) -> Telemetry | None:
        if self._i >= len(self.frames):
            if not self.loop:
                return None
            self._i = 0
        frame = self.frames[self._i]
        self._i += 1
        return frame

    def __iter__(self) -> Iterator[Telemetry]:
        while True:
            f = self.read()
            if f is None:
                return
            yield f

    def close(self) -> None:
        pass


class SharedMemorySource:
    """The real source: the plugin's memory-mapped file.

    Deliberately not implemented against guessed offsets. The layout comes from the
    plugin's own header -- see bridge/layout.py and `python -m bridge probe`.
    """

    DEFAULT_NAME = "Local\\SCSTelemetry"

    def __init__(self, name: str = DEFAULT_NAME, layout=None) -> None:
        self.name = name
        self.layout = layout
        if layout is None:
            raise NotImplementedError(
                "No struct layout loaded.\n"
                "  The plugin's field offsets are not something to guess -- a wrong offset\n"
                "  decodes to a plausible number rather than an error.\n"
                "  Generate one from the plugin header:\n"
                "      python -m bridge layout scs-telemetry-common.hpp -o layouts/rencloud.json\n"
                "  then verify it against the running game:\n"
                "      python -m bridge probe --layout layouts/rencloud.json"
            )

    def read(self) -> Telemetry | None:  # pragma: no cover - needs the game
        raise NotImplementedError

    def close(self) -> None:
        pass
