import unittest

from bridge.scale import DEFAULT_HIGHWAY_SCALE, ScaleEstimator


def feed(est, seconds, scale, start_real=0.0, start_game=0.0, step=0.05):
    """Drive the estimator for `seconds` of real time at a given game/real ratio."""
    real, game = start_real, start_game
    n = int(seconds / step)
    for _ in range(n):
        real += step
        game += step / 60.0 * scale
        est.update(real, game)
    return real, game


class TestMeasurement(unittest.TestCase):
    def test_measures_a_steady_ratio(self):
        est = ScaleEstimator()
        feed(est, 10, 20.0)
        self.assertAlmostEqual(est.measured, 20.0, places=2)

    def test_unknown_before_enough_samples(self):
        self.assertIsNone(ScaleEstimator().measured)

    def test_paused_when_game_time_stops(self):
        est = ScaleEstimator()
        feed(est, 10, 0.0)
        self.assertTrue(est.paused)
        self.assertLess(est.measured, 0.05)

    def test_window_forgets_old_samples(self):
        est = ScaleEstimator(window_s=5.0)
        real, game = feed(est, 20, 3.0)
        feed(est, 10, 20.0, start_real=real, start_game=game)
        self.assertAlmostEqual(est.measured, 20.0, places=1)


class TestOutliers(unittest.TestCase):
    def test_discards_fast_forward(self):
        """Sleeping advances nine game hours in a second. That must not become the average."""
        est = ScaleEstimator()
        real, game = feed(est, 10, 20.0)
        est.update(real + 1.0, game + 9 * 60)          # a nine-hour rest
        real, game = feed(est, 5, 20.0, start_real=real + 1.0, start_game=game + 9 * 60)
        self.assertEqual(est.discarded, 1)
        self.assertAlmostEqual(est.measured, 20.0, places=1)

    def test_resets_on_backwards_jump(self):
        est = ScaleEstimator()
        real, game = feed(est, 10, 20.0)
        est.update(real + 0.05, game - 500)            # loaded an earlier save
        self.assertEqual(est.resets, 1)
        self.assertIsNone(est.measured)

    def test_ignores_duplicate_frames(self):
        est = ScaleEstimator()
        est.update(1.0, 10.0)
        est.update(1.0, 10.0)
        est.update(0.5, 9.0)
        self.assertIsNone(est.measured)


class TestEffective(unittest.TestCase):
    def test_prefers_the_reported_channel(self):
        """The channel reacts instantly at a city boundary; the average lags by the window."""
        est = ScaleEstimator()
        feed(est, 10, 20.0)
        self.assertEqual(est.effective(3.0), 3.0)

    def test_falls_back_to_measurement(self):
        est = ScaleEstimator()
        feed(est, 10, 20.0)
        self.assertAlmostEqual(est.effective(None), 20.0, places=1)
        self.assertAlmostEqual(est.effective(0.0), 20.0, places=1)
        self.assertAlmostEqual(est.effective(9999.0), 20.0, places=1)

    def test_none_when_paused_and_unreported(self):
        est = ScaleEstimator()
        feed(est, 10, 0.0)
        self.assertIsNone(est.effective(None))


class TestCruiseMemory(unittest.TestCase):
    def test_defaults_before_any_sample(self):
        self.assertEqual(ScaleEstimator().cruise_scale, DEFAULT_HIGHWAY_SCALE)

    def test_remembers_open_road(self):
        est = ScaleEstimator()
        for _ in range(400):
            est.note(20.0, 25.0)
        self.assertAlmostEqual(est.cruise_scale, 20.0, places=1)
        self.assertAlmostEqual(est.highway_speed_ms, 25.0, places=1)

    def test_city_samples_do_not_erase_it(self):
        est = ScaleEstimator()
        for _ in range(400):
            est.note(20.0, 25.0)
        for _ in range(400):
            est.note(3.0, 14.0)                        # a long crawl through town
        self.assertAlmostEqual(est.cruise_scale, 20.0, places=1)
        self.assertAlmostEqual(est.highway_speed_ms, 25.0, places=1)


if __name__ == "__main__":
    unittest.main()
