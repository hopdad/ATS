"""The normalised telemetry frame everything downstream works from.

Units are SI, matching what the game reports: metres, metres per second, litres,
kilograms, kelvin-free celsius, and minutes for game time. Conversion to miles and
gallons happens at the presentation edge, so an ETS2 user in metric costs nothing.

Nothing in this module knows where a frame came from. That is what lets the whole
pipeline be developed and tested against a simulator with no game running.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Job:
    source_city: str = ""
    source_company: str = ""
    dest_city: str = ""
    dest_company: str = ""
    cargo: str = ""
    cargo_mass_kg: float = 0.0
    income: float = 0.0
    # Game minutes, absolute on the same clock as Telemetry.game_time_min.
    delivery_deadline_min: float = 0.0
    remaining_distance_m: float = 0.0
    on_job: bool = False


@dataclass
class Damage:
    truck: float = 0.0        # 0.0 - 1.0
    trailer: float = 0.0
    cargo: float = 0.0
    wheels: float = 0.0

    @property
    def worst(self) -> float:
        return max(self.truck, self.trailer, self.cargo, self.wheels)


@dataclass
class Switches:
    """Live switch state, for closed-loop buttons. None means the source does not report it."""
    parking_brake: bool | None = None
    engine_running: bool | None = None
    electric_on: bool | None = None
    low_beam: bool | None = None
    high_beam: bool | None = None
    beacon: bool | None = None
    hazard: bool | None = None
    blinker_left: bool | None = None
    blinker_right: bool | None = None
    differential_lock: bool | None = None
    lift_axle: bool | None = None
    lift_axle_trailer: bool | None = None
    cruise_on: bool | None = None
    cruise_speed_ms: float = 0.0
    retarder_level: int = 0
    retarder_steps: int = 3
    wipers: bool | None = None
    trailer_attached: bool | None = None


@dataclass
class Telemetry:
    """One decoded frame."""

    # --- movement ---
    speed_ms: float = 0.0
    speed_limit_ms: float = 0.0      # 0 when the game reports no limit
    rpm: float = 0.0
    rpm_max: float = 2500.0
    gear: int = 0                    # negative = reverse, 0 = neutral
    gear_ratio_count: int = 12

    # --- consumables and health ---
    fuel_l: float = 0.0
    fuel_capacity_l: float = 0.0
    fuel_avg_consumption_lpkm: float = 0.0
    air_pressure_psi: float = 0.0
    oil_pressure_psi: float = 0.0
    oil_temp_c: float = 0.0
    water_temp_c: float = 0.0
    battery_v: float = 0.0
    adblue_l: float = 0.0

    # --- time ---
    game_time_min: float = 0.0       # absolute game minutes
    local_scale: float = 0.0         # game seconds per real second, as reported (0 = unknown)
    next_rest_min: float = 0.0       # game minutes until rest is required

    # --- context ---
    job: Job = field(default_factory=Job)
    damage: Damage = field(default_factory=Damage)
    switches: Switches = field(default_factory=Switches)

    # --- source health, set by the bridge rather than the game ---
    paused: bool = False
    connected: bool = True
    received_at: float = 0.0         # real monotonic seconds

    def to_dict(self) -> dict:
        return asdict(self)


MS_PER_MPH = 0.44704
L_PER_GAL = 3.785411784
M_PER_MILE = 1609.344


def mph(speed_ms: float) -> float:
    return speed_ms / MS_PER_MPH


def gallons(litres: float) -> float:
    return litres / L_PER_GAL


def miles(metres: float) -> float:
    return metres / M_PER_MILE
