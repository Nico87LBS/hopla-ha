"""Speed bonus (chrono) events."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"
spec = importlib.util.spec_from_file_location("hopla_chrono", ROOT / "chrono.py")
chrono = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chrono)

NOW = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
MEMBERS = [SimpleNamespace(user_id=2, display_name="Elena", username="elena"),
           SimpleNamespace(user_id=3, display_name="", username="anna")]


def task(id, user, flash=None, due=None, name="Brosser les dents"):
    return SimpleNamespace(id=id, name=name, points=2, assigned_to=user, assignee_ids=[user],
                           next_due_date=due, flash=flash)


def live(minutes=15, live_id=7):
    return {"points": 5, "endsAt": (NOW + timedelta(minutes=minutes)).isoformat(), "liveId": live_id}


class Clock:
    def __init__(self):
        self.now = NOW
        self.timers = []

    def schedule(self, when, action):
        timer = [when, action, True]
        self.timers.append(timer)

        def cancel():
            timer[2] = False
        return cancel

    def run_until(self, moment):
        self.now = moment
        for timer in sorted(self.timers, key=lambda item: item[0]):
            if timer[2] and timer[0] <= moment:
                timer[2] = False
                timer[1]()


class ChronoTrackerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.events = []
        self.tracker = chrono.ChronoTracker(self.clock.schedule, lambda event, data: self.events.append((event, data)),
                                            now=lambda: self.clock.now)

    def names(self):
        return [event for event, _ in self.events]

    def test_the_first_refresh_does_not_announce_what_already_runs(self):
        self.tracker.update([task(1, 2, live())], MEMBERS, "e")
        self.assertEqual(self.events, [])
        self.clock.run_until(NOW + timedelta(minutes=15))
        self.assertEqual(self.names(), ["hopla_chrono_ended"])

    def test_a_chrono_a_parent_starts_is_announced_once_for_every_copy(self):
        self.tracker.update([], MEMBERS, "e")
        self.tracker.update([task(1, 2, live()), task(4, 3, live())], MEMBERS, "e")
        self.tracker.update([task(1, 2, live()), task(4, 3, live())], MEMBERS, "e")
        self.assertEqual(self.names(), ["hopla_chrono_started"])
        data = self.events[0][1]
        self.assertEqual(data["assignee_names"], ["Elena", "anna"])
        self.assertEqual(data["minutes_left"], 15)
        self.assertTrue(data["launched"])
        self.assertEqual(data["config_entry_id"], "e")

    def test_a_task_done_or_a_chrono_stopped_ends_without_an_event(self):
        self.tracker.update([], MEMBERS, "e")
        self.tracker.update([task(1, 2, live())], MEMBERS, "e")
        self.tracker.update([task(1, 2)], MEMBERS, "e")
        self.clock.run_until(NOW + timedelta(minutes=20))
        self.assertEqual(self.names(), ["hopla_chrono_started"])

    def test_a_task_own_chrono_starts_at_its_due_time(self):
        due = NOW + timedelta(minutes=30)
        own = {"points": 3, "endsAt": (due + timedelta(minutes=10)).isoformat()}
        self.tracker.update([], MEMBERS, "e")
        self.tracker.update([task(1, 2, own, due)], MEMBERS, "e")
        self.assertEqual(self.events, [])
        self.clock.run_until(due)
        self.tracker.update([task(1, 2, own, due)], MEMBERS, "e")
        self.assertEqual(self.names(), ["hopla_chrono_started"])
        self.assertFalse(self.events[0][1]["launched"])
        self.assertEqual(self.events[0][1]["minutes_left"], 10)
        self.clock.run_until(due + timedelta(minutes=10))
        self.assertEqual(self.names(), ["hopla_chrono_started", "hopla_chrono_ended"])

    def test_a_new_chrono_replacing_one_is_announced(self):
        self.tracker.update([task(1, 2, live())], MEMBERS, "e")
        self.tracker.update([task(1, 2, live(30, live_id=8))], MEMBERS, "e")
        self.clock.run_until(NOW + timedelta(minutes=15))
        self.assertEqual(self.names(), ["hopla_chrono_started"])
        self.assertEqual(self.events[0][1]["minutes_left"], 30)


if __name__ == "__main__":
    unittest.main()
