"""Measuring how fast game time runs against real time.

The game reports a `local_scale` channel, but it is not the whole story: the factor
changes with where you are (roughly 20x on open road, roughly 3x inside a city), it
goes meaningless while paused, and a time-scale mod can move it anywhere. So the
bridge also *measures* the ratio from the frames it already has, which costs nothing
and needs no cooperation from the plugin.

Three things the naive version gets wrong, all handled here:

  paused          game time stops, the ratio collapses to zero, any estimate built on
                  it goes to infinity. Reported as paused, never as a number.
  sleep / ferry   game time fast-forwards hours in a second. Those samples are
                  discarded rather than allowed to poison the average.
  save reload     game time can jump backwards or far forwards. Treated as a
                  discontinuity: the window resets instead of averaging across it.
"""

from __future__ import annotations

from collections import deque

# A scale above this is a fast-forward (sleeping, ferry, train), not driving.
FAST_FORWARD_SCALE = 60.0
# Below this, game time is effectively stopped.
PAUSED_SCALE = 0.05
# Above this, we are on open road rather than inside a city.
HIGHWAY_MIN_SCALE = 6.0
# Used only until real open-road samples arrive.
DEFAULT_HIGHWAY_SCALE = 20.0


class ScaleEstimator:
    """Rolling estimate of game minutes elapsed per real minute."""

    def __init__(self, window_s: float = 45.0, min_samples: int = 3) -> None:
        self.window_s = window_s
        self.min_samples = min_samples
        self._samples: deque[tuple[float, float]] = deque()  # (real_s, game_min)
        self._last: tuple[float, float] | None = None
        self.discarded = 0
        self.resets = 0
        # What open road looks like, remembered so that passing through a town does not
        # rewrite the estimate for the 100 miles of highway still to come.
        self.highway_scale: float | None = None
        self.highway_speed_ms: float | None = None

    def reset(self) -> None:
        self._samples.clear()
        self._last = None
        self.resets += 1

    def update(self, real_s: float, game_min: float) -> None:
        """Feed one frame. `real_s` is a monotonic clock, `game_min` absolute game minutes."""
        if self._last is not None:
            prev_real, prev_game = self._last
            d_real = real_s - prev_real
            d_game = game_min - prev_game
            if d_real <= 0:
                return                                  # duplicate or out-of-order frame

            # Either kind of jump makes the samples already in the window incomparable
            # with the ones after it -- the window spans the gap, so it has to be dropped,
            # not just the offending frame. The two cases differ only in what they mean.
            if d_game < 0:                              # loaded an earlier save
                self._last = (real_s, game_min)
                self._samples.clear()
                self.resets += 1
                return
            if d_game / (d_real / 60.0) > FAST_FORWARD_SCALE:   # sleeping, ferry, train
                self._last = (real_s, game_min)
                self._samples.clear()
                self.discarded += 1
                return

        self._last = (real_s, game_min)
        self._samples.append((real_s, game_min))
        cutoff = real_s - self.window_s
        while len(self._samples) > 2 and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def note(self, scale: float | None, speed_ms: float) -> None:
        """Record open-road conditions. Ignores anything that looks like city driving."""
        if scale is None or not (HIGHWAY_MIN_SCALE < scale <= FAST_FORWARD_SCALE):
            return
        self.highway_scale = scale if self.highway_scale is None else \
            self.highway_scale * 0.98 + scale * 0.02
        if speed_ms > 0:
            self.highway_speed_ms = speed_ms if self.highway_speed_ms is None else \
                self.highway_speed_ms * 0.98 + speed_ms * 0.02

    @property
    def cruise_scale(self) -> float:
        """The scale to assume for road not yet reached."""
        return self.highway_scale if self.highway_scale is not None else DEFAULT_HIGHWAY_SCALE

    @property
    def measured(self) -> float | None:
        """Game minutes per real minute over the window, or None if not yet known."""
        if len(self._samples) < self.min_samples:
            return None
        (first_real, first_game), (last_real, last_game) = self._samples[0], self._samples[-1]
        d_real_min = (last_real - first_real) / 60.0
        if d_real_min <= 0:
            return None
        return (last_game - first_game) / d_real_min

    @property
    def paused(self) -> bool:
        m = self.measured
        return m is not None and m < PAUSED_SCALE

    def effective(self, reported: float | None = None) -> float | None:
        """The scale to actually use.

        The reported channel wins when it looks sane, because it reacts instantly to a
        city boundary where the measured average lags by the window. The measurement is
        the fallback, and the arbiter when the channel is missing or implausible.
        """
        if reported is not None and PAUSED_SCALE < reported <= FAST_FORWARD_SCALE:
            return reported
        m = self.measured
        if m is None or m < PAUSED_SCALE:
            return None
        return m
