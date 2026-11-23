"""Announcements before a routine, a moment or a task starts or ends."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"
spec = importlib.util.spec_from_file_location("hopla_notices", ROOT / "notices.py")
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)

NOW = datetime(2026, 11, 23, 7, 0, tzinfo=timezone.utc)
MEMBERS = [SimpleNamespace(user_id=2, display_name="Elena", username="elena"),
           SimpleNamespace(user_id=3, display_name="", username="anna")]


def at(minutes):
    return (NOW + timedelta(minutes=minutes)).isoformat()


def routine(window="open", opens=-30, closes=30, finished=(False, False)):
    return {"id": 1, "name": "Matin", "window": window, "opens_at": at(opens), "closes_at": at(closes),
            "members": [{"user_id": uid, "total": 3, "finished": done} for uid, done in zip((2, 3), finished)]}


def task(id=5, slots=None, deadline=None, due=0, active=True):
    return SimpleNamespace(id=id, name="Brosser les dents", points=2, is_active=active, members_now=[2],
                           slots_today=slots or [], deadline=deadline, next_due_date=NOW + timedelta(minutes=due))


class Clock:
    def __init__(self):
        self.now = NOW
        self.timers = []
        self.fired = []

    def schedule(self, when, action):
        timer = [when, action, True]
        self.timers.append(timer)
        return lambda: timer.__setitem__(2, False)

    def run_until(self, minutes):
        self.now = NOW + timedelta(minutes=minutes)
        for timer in sorted(self.timers, key=lambda item: item[0]):
            if timer[2] and timer[0] <= self.now:
                timer[2] = False
                timer[1]()

    def fire(self, event, data):
        self.fired.append((event, data))


class MinutesTests(unittest.TestCase):
    def test_minutes_are_read_largest_first_without_junk(self):
        self.assertEqual(notices.parse_minutes("5, 10;x,0,10"), [10, 5])
        self.assertEqual(notices.parse_minutes(""), [])
        self.assertEqual(notices.parse_minutes(None), [])


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.scheduler = notices.NoticeScheduler(self.clock.schedule, self.clock.fire, lambda: self.clock.now)

    def update(self, tasks=(), routines=(), minutes="10,5"):
        self.scheduler.update(list(tasks), {"routines": list(routines)}, MEMBERS, "e1", minutes)

    def kinds(self):
        return [(d["item_type"], d["edge"], d["kind"], d["offset_minutes"]) for _, d in self.clock.fired]

    def test_an_open_routine_is_announced_before_its_end_and_at_its_end(self):
        self.update(routines=[routine()])
        self.clock.run_until(60)
        self.assertEqual(self.kinds(), [("routine", "end", "before", 10), ("routine", "end", "before", 5),
                                        ("routine", "end", "now", 0)])
        data = self.clock.fired[0][1]
        self.assertEqual((data["item_name"], data["member_names"], data["config_entry_id"]), ("Matin", ["Elena", "anna"], "e1"))

    def test_a_routine_to_come_is_announced_before_it_opens_too(self):
        self.update(routines=[routine("upcoming", opens=20, closes=60)])
        self.clock.run_until(20)
        self.assertEqual([k for k in self.kinds() if k[1] == "start"],
                         [("routine", "start", "before", 10), ("routine", "start", "before", 5), ("routine", "start", "now", 0)])

    def test_nothing_fires_for_hours_already_past(self):
        self.update(routines=[routine("over", opens=-90, closes=-30)])
        self.clock.run_until(60)
        self.assertEqual(self.clock.fired, [])

    def test_a_routine_everyone_finished_is_not_announced(self):
        self.update(routines=[routine(finished=(True, True))])
        self.clock.run_until(60)
        self.assertEqual(self.clock.fired, [])

    def test_a_routine_finished_in_the_meantime_cancels_its_announcements(self):
        self.update(routines=[routine()])
        self.update(routines=[routine(finished=(True, True))])
        self.clock.run_until(60)
        self.assertEqual(self.clock.fired, [])

    def test_only_unfinished_children_are_named(self):
        self.update(routines=[routine(finished=(True, False))])
        self.clock.run_until(60)
        self.assertEqual(self.clock.fired[0][1]["member_names"], ["anna"])

    def test_a_moment_still_to_do_is_announced_but_a_done_one_is_not(self):
        slots = [{"slotId": "m", "name": "Matin", "state": "open", "opensAt": at(-30), "closesAt": at(15)},
                 {"slotId": "s", "name": "Soir", "state": "done", "opensAt": at(-30), "closesAt": at(15)}]
        self.update(tasks=[task(slots=slots)])
        self.clock.run_until(60)
        self.assertEqual(self.kinds(), [("moment", "end", "before", 10), ("moment", "end", "before", 5),
                                        ("moment", "end", "now", 0)])
        self.assertEqual(self.clock.fired[0][1]["slot_name"], "Matin")

    def test_a_task_with_a_deadline_starts_at_its_due_time_and_ends_at_its_deadline(self):
        self.update(tasks=[task(due=30, deadline=NOW + timedelta(minutes=45))], minutes="")
        self.clock.run_until(60)
        self.assertEqual(self.kinds(), [("task", "start", "now", 0), ("task", "end", "now", 0)])

    def test_a_task_without_deadline_is_left_to_its_own_reminders(self):
        self.update(tasks=[task()])
        self.clock.run_until(60)
        self.assertEqual(self.clock.fired, [])

    def test_a_rescheduled_end_replaces_the_old_timers(self):
        self.update(routines=[routine(closes=30)])
        self.update(routines=[routine(closes=45)])
        self.clock.run_until(60)
        ends = [d["at"] for _, d in self.clock.fired if d["kind"] == "now"]
        self.assertEqual(ends, [at(45)])

    def test_no_minutes_keeps_only_the_announcement_at_the_edge(self):
        self.update(routines=[routine()], minutes="")
        self.clock.run_until(60)
        self.assertEqual(self.kinds(), [("routine", "end", "now", 0)])


if __name__ == "__main__":
    unittest.main()
