import json
import tempfile
import unittest
from pathlib import Path

from bridge import record
from bridge.model import M_PER_MILE, Telemetry
from bridge.sources import ReplaySource, SimulatedSource


class TestRoundTrip(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "run.jsonl"

    def tearDown(self):
        self.dir.cleanup()

    def test_nested_dataclasses_survive(self):
        t = Telemetry()
        t.speed_ms = 24.5
        t.job.dest_city = "Barstow"
        t.job.remaining_distance_m = 100 * M_PER_MILE
        t.job.on_job = True
        t.damage.trailer = 0.07
        t.switches.low_beam = True
        t.switches.retarder_level = 2

        with record.Recorder(self.path) as rec:
            rec.write(t)

        back = record.load(self.path)[0]
        self.assertAlmostEqual(back.speed_ms, 24.5)
        self.assertEqual(back.job.dest_city, "Barstow")
        self.assertTrue(back.job.on_job)
        self.assertAlmostEqual(back.damage.trailer, 0.07)
        self.assertTrue(back.switches.low_beam)
        self.assertEqual(back.switches.retarder_level, 2)

    def test_records_a_simulated_run(self):
        src = SimulatedSource(speed_factor=50.0)
        with record.Recorder(self.path) as rec:
            for _ in range(25):
                rec.write(src.read())
        frames = record.load(self.path)
        self.assertEqual(len(frames), 25)
        self.assertGreater(frames[0].job.remaining_distance_m, frames[-1].job.remaining_distance_m)

    def test_blank_lines_are_skipped(self):
        self.path.write_text(json.dumps(record.to_dict(Telemetry())) + "\n\n\n")
        self.assertEqual(len(record.load(self.path)), 1)

    def test_bad_line_names_its_number(self):
        self.path.write_text(json.dumps(record.to_dict(Telemetry())) + "\nnot json\n")
        with self.assertRaises(ValueError) as ctx:
            record.load(self.path)
        self.assertIn(":2:", str(ctx.exception))

    def test_unknown_fields_are_ignored(self):
        """A recording from a later version must not crash an older bridge."""
        d = record.to_dict(Telemetry())
        d["invented_later"] = 7
        d["job"]["also_invented"] = "x"
        self.path.write_text(json.dumps(d) + "\n")
        self.assertEqual(len(record.load(self.path)), 1)


class TestReplay(unittest.TestCase):
    def test_plays_once_then_stops(self):
        src = ReplaySource([Telemetry(), Telemetry()])
        self.assertIsNotNone(src.read())
        self.assertIsNotNone(src.read())
        self.assertIsNone(src.read())

    def test_loops_when_asked(self):
        src = ReplaySource([Telemetry()], loop=True)
        self.assertIsNotNone(src.read())
        self.assertIsNotNone(src.read())

    def test_iterates(self):
        self.assertEqual(len(list(ReplaySource([Telemetry()] * 3))), 3)

    def test_rejects_an_empty_recording(self):
        with self.assertRaises(ValueError):
            ReplaySource([])


class TestSimulator(unittest.TestCase):
    def test_produces_a_loaded_truck(self):
        t = SimulatedSource().read()
        self.assertTrue(t.job.on_job)
        self.assertGreater(t.speed_ms, 0)
        self.assertGreater(t.local_scale, 0)
        self.assertEqual(t.job.dest_city, "Barstow")

    def test_burns_fuel_and_covers_ground(self):
        src = SimulatedSource(speed_factor=200.0)
        first = src.read()
        for _ in range(40):
            last = src.read()
        self.assertLess(last.fuel_l, first.fuel_l)
        self.assertLess(last.job.remaining_distance_m, first.job.remaining_distance_m)
        self.assertGreater(last.game_time_min, first.game_time_min)


if __name__ == "__main__":
    unittest.main()
