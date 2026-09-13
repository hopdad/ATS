import unittest

from bridge.derive import (AlertTracker, Config, constraints, frame,
                           pay_per_real_hour, real_minutes_for, real_minutes_of)
from bridge.model import M_PER_MILE, MS_PER_MPH, Telemetry

MPH55 = 55 * MS_PER_MPH
CFG = Config()


def loaded(**kw) -> Telemetry:
    t = Telemetry()
    t.speed_ms = kw.get("speed", MPH55)
    t.speed_limit_ms = kw.get("limit", MPH55)
    t.fuel_l = kw.get("fuel_l", 250.0)
    t.fuel_capacity_l = 568.0
    t.fuel_avg_consumption_lpkm = 0.38
    t.air_pressure_psi = kw.get("air", 118.0)
    t.game_time_min = kw.get("now", 0.0)
    t.next_rest_min = kw.get("rest", 600.0)
    t.job.on_job = True
    t.job.income = kw.get("income", 4180.0)
    t.job.remaining_distance_m = kw.get("distance", 100 * M_PER_MILE)
    t.job.delivery_deadline_min = kw.get("deadline", 5000.0)
    t.received_at = kw.get("at", 0.0)
    return t


class TestRealTime(unittest.TestCase):
    def test_open_road(self):
        """96 highway miles at 55 mph and 20x is 5.2 real minutes, and the 4-mile city
        approach at 30 mph and 3x adds another 2.7 -- the approach is a third of the cost."""
        got = real_minutes_for(100 * M_PER_MILE, MPH55, 20.0, CFG, cruise_scale=20.0)
        self.assertAlmostEqual(got, 7.9, delta=0.3)

    def test_city_approach_costs_more_per_mile(self):
        """The last miles run at city scale, so they cost several times more real time."""
        hwy = real_minutes_for(4 * M_PER_MILE, MPH55, 20.0, CFG, is_approach=False, cruise_scale=20.0)
        city = real_minutes_for(4 * M_PER_MILE, MPH55, 3.0, CFG, is_approach=True)
        self.assertGreater(city, hwy * 4)

    def test_final_approach_uses_the_current_scale(self):
        got = real_minutes_for(2 * M_PER_MILE, 30 * MS_PER_MPH, 3.0, CFG)
        self.assertAlmostEqual(got, (2 / 30 * 60) / 3.0, places=3)

    def test_passing_through_a_town_does_not_blow_up_the_estimate(self):
        """Regression: costing 100 remaining miles at city scale tripled the estimate
        the moment the truck passed through a town nowhere near the destination."""
        far = 100 * M_PER_MILE
        on_road = real_minutes_for(far, MPH55, 20.0, CFG, cruise_scale=20.0, cruise_speed_ms=MPH55)
        in_town = real_minutes_for(far, 30 * MS_PER_MPH, 3.0, CFG,
                                   cruise_scale=20.0, cruise_speed_ms=MPH55)
        self.assertAlmostEqual(on_road, in_town, delta=0.3)

    def test_none_when_stopped(self):
        self.assertIsNone(real_minutes_for(10 * M_PER_MILE, 0.0, 20.0, CFG))

    def test_none_without_a_scale(self):
        self.assertIsNone(real_minutes_for(10 * M_PER_MILE, MPH55, None, CFG))

    def test_zero_distance(self):
        self.assertEqual(real_minutes_for(0.0, MPH55, 20.0, CFG), 0.0)

    def test_duration_conversion(self):
        self.assertAlmostEqual(real_minutes_of(600.0, 20.0), 30.0)
        self.assertIsNone(real_minutes_of(600.0, None))
        self.assertIsNone(real_minutes_of(600.0, 0.0))


class TestPay(unittest.TestCase):
    def test_per_real_hour(self):
        self.assertAlmostEqual(pay_per_real_hour(4180.0, 30.0), 8360.0)

    def test_none_without_a_time(self):
        self.assertIsNone(pay_per_real_hour(4180.0, None))
        self.assertIsNone(pay_per_real_hour(4180.0, 0.0))

    def test_none_without_income(self):
        self.assertIsNone(pay_per_real_hour(0.0, 30.0))


class TestConstraints(unittest.TestCase):
    def test_sorted_soonest_first(self):
        cons = constraints(loaded(), 20.0, CFG)
        self.assertEqual([c.game_minutes for c in cons], sorted(c.game_minutes for c in cons))

    def test_rest_can_bite_before_arrival(self):
        cons = constraints(loaded(rest=30.0), 20.0, CFG)
        self.assertEqual(cons[0].key, "rest")

    def test_deadline_omitted_once_passed(self):
        cons = constraints(loaded(now=6000.0, deadline=5000.0), 20.0, CFG)
        self.assertNotIn("deadline", [c.key for c in cons])

    def test_no_job_means_no_job_constraints(self):
        t = loaded()
        t.job.on_job = False
        self.assertEqual(sorted(c.key for c in constraints(t, 20.0, CFG)), ["fuel", "rest"])


class TestAlerts(unittest.TestCase):
    def test_quiet_when_nothing_is_wrong(self):
        tr = AlertTracker()
        t = loaded()
        tr.update(t)
        self.assertEqual(tr.alerts(t, CFG), [])

    def test_over_limit_needs_to_persist(self):
        tr = AlertTracker()
        t = loaded(speed=70 * MS_PER_MPH, limit=MPH55, at=0.0)
        tr.update(t)
        self.assertEqual(tr.alerts(t, CFG), [])
        t.received_at = 5.0
        tr.update(t)
        self.assertEqual(tr.alerts(t, CFG), [])
        t.received_at = 15.0
        tr.update(t)
        self.assertEqual([a["code"] for a in tr.alerts(t, CFG)], ["over_limit"])

    def test_over_limit_clears_on_slowing(self):
        tr = AlertTracker()
        t = loaded(speed=70 * MS_PER_MPH, at=0.0)
        tr.update(t)
        t.received_at = 20.0
        tr.update(t)
        t.speed_ms = MPH55 - 1
        t.received_at = 21.0
        tr.update(t)
        self.assertEqual(tr.alerts(t, CFG), [])

    def test_low_air(self):
        tr = AlertTracker()
        t = loaded(air=78.0)
        tr.update(t)
        self.assertIn("air", [a["code"] for a in tr.alerts(t, CFG)])

    def test_damage_step_reports_once(self):
        tr = AlertTracker()
        t = loaded()
        tr.update(t)
        tr.alerts(t, CFG)
        t.damage.trailer = 0.12
        self.assertIn("damage", [a["code"] for a in tr.alerts(t, CFG)])
        self.assertNotIn("damage", [a["code"] for a in tr.alerts(t, CFG)])


class TestFrame(unittest.TestCase):
    def setUp(self):
        self.f = frame(loaded(), 20.0, CFG, AlertTracker(), cruise_scale=20.0)

    def test_us_units(self):
        self.assertAlmostEqual(self.f["speed"], 55.0, places=1)
        self.assertAlmostEqual(self.f["distance_remaining"], 100.0, places=1)

    def test_metric_units(self):
        f = frame(loaded(), 20.0, Config(units="metric"), AlertTracker())
        self.assertAlmostEqual(f["speed"], 88.5, delta=0.3)

    def test_carries_the_derived_answers(self):
        self.assertIsNotNone(self.f["real_minutes_left"])
        self.assertIsNotNone(self.f["pay_per_real_hour"])
        self.assertEqual(self.f["bites_first"]["key"], "arrive")

    def test_paused_when_scale_unknown(self):
        f = frame(loaded(), None, CFG, AlertTracker())
        self.assertTrue(f["paused"])
        self.assertIsNone(f["real_minutes_left"])
        self.assertIsNone(f["pay_per_real_hour"])

    def test_speed_limit_absent_reads_as_none(self):
        f = frame(loaded(limit=0.0), 20.0, CFG, AlertTracker())
        self.assertIsNone(f["speed_limit"])
        self.assertFalse(f["over_limit"])


if __name__ == "__main__":
    unittest.main()
