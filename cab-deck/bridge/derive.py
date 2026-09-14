"""Everything the dashboard shows that the game does not.

Three derived answers live here, and they are the reason the project exists:

  real time left      every clock in the game is game time. The player wants to know
                      how much of their evening this run costs.
  what bites first    rest, fuel, the delivery window or the destination -- whichever
                      arrives soonest is the only one worth a glance.
  pay per real hour   the payout divided by the real time it costs, which is the only
                      way to compare a long haul against short runs.

All pure functions over a Telemetry frame plus a scale, so they test without a game,
a socket or a clock.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Telemetry, M_PER_MILE, MS_PER_MPH, gallons, miles, mph


@dataclass
class Config:
    """Tunables. The city figures want calibrating against real runs -- see the recorder."""
    # How much of the approach to the destination runs at city time scale.
    city_distance_m: float = 4 * M_PER_MILE
    city_speed_ms: float = 30 * MS_PER_MPH
    city_scale: float = 3.0
    # Below this many game-seconds-per-real-second we are already in town.
    in_city_scale: float = 4.5
    units: str = "us"


def _game_minutes(distance_m: float, speed_ms: float) -> float:
    """Game minutes to cover a distance, or inf when stopped."""
    if speed_ms <= 0.1:
        return float("inf")
    return distance_m / speed_ms / 60.0


def real_minutes_for(distance_m: float, speed_ms: float, scale: float | None,
                     cfg: Config, is_approach: bool = True,
                     cruise_scale: float | None = None,
                     cruise_speed_ms: float | None = None) -> float | None:
    """Real minutes to cover `distance_m`, accounting for the city scale near the end.

    Game time runs far faster on the open road than inside a city, so dividing the whole
    journey by the current scale is wrong exactly where it matters -- the final miles,
    where each game minute costs several times more of the player's actual life.

    The trap is the other direction. Passing *through* a town 100 miles out drops the
    current scale to city pace, and costing the remaining hundred miles at that pace
    triples the estimate for no reason. So only the stretch you are actually in uses the
    current scale; road not yet reached is costed at remembered open-road pace.
    """
    if scale is None or scale <= 0:
        return None
    if distance_m <= 0:
        return 0.0

    # On the final approach the current scale is the right one for all that is left.
    if is_approach and distance_m <= cfg.city_distance_m:
        g = _game_minutes(distance_m, speed_ms)
        return None if g == float("inf") else g / scale

    hw_scale = cruise_scale if cruise_scale else (scale if scale > cfg.in_city_scale else 20.0)
    hw_speed = max(speed_ms, cruise_speed_ms or 0.0)

    city_m = cfg.city_distance_m if is_approach else 0.0
    hwy_m = max(0.0, distance_m - city_m)

    hwy_game = _game_minutes(hwy_m, hw_speed)
    if hwy_game == float("inf"):
        return None
    city_game = _game_minutes(city_m, cfg.city_speed_ms)
    return hwy_game / hw_scale + city_game / cfg.city_scale


def real_minutes_of(game_minutes: float, scale: float | None) -> float | None:
    """Convert a game-time duration that is not a distance -- a rest timer, a deadline."""
    if scale is None or scale <= 0 or game_minutes is None:
        return None
    return game_minutes / scale


def pay_per_real_hour(income: float, real_minutes: float | None) -> float | None:
    """What the job pays per hour of the player's life, not the driver's."""
    if not income or real_minutes is None or real_minutes <= 0:
        return None
    return income / (real_minutes / 60.0)


@dataclass
class Constraint:
    key: str
    label: str
    game_minutes: float
    real_minutes: float | None

    @property
    def urgent(self) -> bool:
        return self.real_minutes is not None and self.real_minutes < 3.0


def constraints(t: Telemetry, scale: float | None, cfg: Config,
                cruise_scale: float | None = None,
                cruise_speed_ms: float | None = None) -> list[Constraint]:
    """Every deadline in play, soonest first."""
    out: list[Constraint] = []
    speed = t.speed_ms

    if t.next_rest_min > 0:
        out.append(Constraint("rest", "Rest stop", t.next_rest_min,
                              real_minutes_of(t.next_rest_min, scale)))

    if t.fuel_avg_consumption_lpkm > 0 and t.fuel_l > 0:
        range_m = (t.fuel_l / t.fuel_avg_consumption_lpkm) * 1000.0
        g = _game_minutes(range_m, speed)
        if g != float("inf"):
            out.append(Constraint("fuel", "Out of fuel", g,
                                  real_minutes_for(range_m, speed, scale, cfg, False,
                                                   cruise_scale, cruise_speed_ms)))

    if t.job.on_job:
        due = t.job.delivery_deadline_min - t.game_time_min
        if due > 0:
            out.append(Constraint("deadline", "Delivery window", due,
                                  real_minutes_of(due, scale)))
        g = _game_minutes(t.job.remaining_distance_m, speed)
        if g != float("inf"):
            out.append(Constraint("arrive", "Arrive", g,
                                  real_minutes_for(t.job.remaining_distance_m, speed, scale, cfg,
                                                   True, cruise_scale, cruise_speed_ms)))

    out.sort(key=lambda c: c.game_minutes)
    return out


class AlertTracker:
    """Alerts need a little memory: how long you have been speeding, damage since last look.

    The strip is empty in the normal case by design -- the screen space is reserved for
    trouble rather than spent on gauges that read the same all day.
    """

    OVER_LIMIT_GRACE_S = 8.0

    def __init__(self) -> None:
        self.over_limit_s = 0.0
        self._last_damage = 0.0
        self._last_at: float | None = None

    def update(self, t: Telemetry) -> None:
        if self._last_at is None:
            self._last_at = t.received_at
            self._last_damage = t.damage.worst
            return
        dt = max(0.0, t.received_at - self._last_at)
        self._last_at = t.received_at
        over = t.speed_limit_ms > 0 and t.speed_ms > t.speed_limit_ms + 0.5
        self.over_limit_s = self.over_limit_s + dt if over else 0.0

    def alerts(self, t: Telemetry, cfg: Config) -> list[dict]:
        out: list[dict] = []
        if self.over_limit_s > self.OVER_LIMIT_GRACE_S:
            out.append({"level": "crit", "code": "over_limit",
                        "text": f"Over the limit {int(self.over_limit_s)}s"})
        if 0 < t.air_pressure_psi < 90:
            out.append({"level": "warn", "code": "air",
                        "text": f"Air pressure {t.air_pressure_psi:.0f} psi"})
        if t.water_temp_c > 100:
            out.append({"level": "warn", "code": "water",
                        "text": f"Water {t.water_temp_c:.0f}°C"})
        if 0 < t.battery_v < 23:
            out.append({"level": "warn", "code": "battery",
                        "text": f"Battery {t.battery_v:.1f} V"})
        damage = t.damage.worst
        if damage - self._last_damage > 0.01:
            out.append({"level": "warn", "code": "damage",
                        "text": f"Damage now {damage * 100:.0f}%"})
        self._last_damage = max(self._last_damage, damage)
        return out


def frame(t: Telemetry, scale: float | None, cfg: Config, tracker: AlertTracker,
          cruise_scale: float | None = None, cruise_speed_ms: float | None = None) -> dict:
    """The payload the dashboard renders. Display units applied here, not upstream."""
    us = cfg.units == "us"
    cons = constraints(t, scale, cfg, cruise_scale, cruise_speed_ms)
    first = cons[0] if cons else None

    arrive = next((c for c in cons if c.key == "arrive"), None)
    real_left = arrive.real_minutes if arrive else None
    fuel_range_m = ((t.fuel_l / t.fuel_avg_consumption_lpkm) * 1000.0
                    if t.fuel_avg_consumption_lpkm > 0 else 0.0)

    return {
        "connected": t.connected,
        "paused": t.paused or scale is None,
        "scale": scale,
        "speed": mph(t.speed_ms) if us else t.speed_ms * 3.6,
        "speed_limit": (mph(t.speed_limit_ms) if us else t.speed_limit_ms * 3.6) if t.speed_limit_ms > 0 else None,
        "over_limit": t.speed_limit_ms > 0 and t.speed_ms > t.speed_limit_ms + 0.5,
        "rpm": t.rpm,
        "rpm_max": t.rpm_max,
        "gear": t.gear,
        "fuel": gallons(t.fuel_l) if us else t.fuel_l,
        "fuel_pct": (t.fuel_l / t.fuel_capacity_l * 100.0) if t.fuel_capacity_l else None,
        "fuel_range": miles(fuel_range_m) if us else fuel_range_m / 1000.0,
        "air_psi": t.air_pressure_psi,
        "game_time_min": t.game_time_min,
        "distance_remaining": miles(t.job.remaining_distance_m) if us else t.job.remaining_distance_m / 1000.0,
        "real_minutes_left": real_left,
        "pay_per_real_hour": pay_per_real_hour(t.job.income, real_left),
        "bites_first": None if first is None else {
            "key": first.key, "label": first.label,
            "game_minutes": first.game_minutes, "real_minutes": first.real_minutes,
            "urgent": first.urgent,
        },
        "constraints": [
            {"key": c.key, "label": c.label, "game_minutes": c.game_minutes,
             "real_minutes": c.real_minutes} for c in cons
        ],
        "job": {
            "on_job": t.job.on_job,
            "source_city": t.job.source_city, "dest_city": t.job.dest_city,
            "source_company": t.job.source_company, "dest_company": t.job.dest_company,
            "cargo": t.job.cargo, "income": t.job.income,
        },
        "damage": {"truck": t.damage.truck, "trailer": t.damage.trailer,
                   "cargo": t.damage.cargo, "worst": t.damage.worst},
        "switches": {k: v for k, v in vars(t.switches).items()},
        "alerts": tracker.alerts(t, cfg),
        "units": cfg.units,
    }
