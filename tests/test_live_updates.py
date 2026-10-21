"""Live update stream parsing and task reminders, without a Home Assistant installation."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sse = load("sse")
reminders = load("reminders")

NOW = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)


def task(id=1, due=NOW + timedelta(hours=2), templates=({"value": -30, "unit": "m"},),
         notification=True, active=True, name="Vider le lave-vaisselle", assigned_to=2):
    return SimpleNamespace(id=id, name=name, next_due_date=due, is_active=active,
                           notification=notification, reminder_templates=list(templates),
                           assigned_to=assigned_to, assignee_ids=[2, 3], points=5)


MEMBERS = [SimpleNamespace(user_id=2, display_name="Elena", username="elena"),
           SimpleNamespace(user_id=3, display_name="", username="anna")]


class SSEParserTests(unittest.TestCase):
    def feed(self, *lines):
        parser = sse.SSEParser()
        return [event for line in lines if (event := parser.feed_line(line)) is not None]

    def test_events_end_at_blank_lines(self):
        events = self.feed('data: {"type": "chore.updated"}\n', "\n",
                           ": keep-alive\n", 'data: {"type": "heartbeat"}\r\n', "\r\n")
        self.assertEqual([event["type"] for event in events], ["chore.updated", "heartbeat"])

    def test_multi_line_and_malformed_data(self):
        events = self.feed('data: {"type":\n', 'data: "rewards.updated"}\n', "\n",
                           "data: not json\n", "\n", "\n", "data: [1]\n", "\n")
        self.assertEqual(events, [{"type": "rewards.updated"}])

    def test_only_heartbeats_skip_the_refresh(self):
        self.assertFalse(sse.needs_refresh({"type": "heartbeat"}))
        for kind in ("connection.established", "chore.completed", "rewards.updated", "circle.updated"):
            self.assertTrue(sse.needs_refresh({"type": kind}))

    def test_reconnect_backs_off_up_to_five_minutes(self):
        self.assertEqual([sse.reconnect_delay(n) for n in range(8)], [5, 10, 20, 40, 80, 160, 300, 300])

    def test_completion_details(self):
        event = {"type": "chore.completed", "data": {
            "chore": {"id": 7, "name": "Ranger", "points": 3},
            "user": {"id": 1}, "history": {"status": 1, "completedBy": 2, "points": 4}}}
        self.assertEqual(sse.completion_details(event),
                         {"task_id": 7, "task_name": "Ranger", "points": 4, "completed_by": 2})
        event["data"]["history"]["status"] = 3  # waiting for approval
        self.assertIsNone(sse.completion_details(event))
        self.assertIsNone(sse.completion_details({"type": "chore.updated", "data": {}}))


class ReminderTests(unittest.TestCase):
    def test_offsets_follow_the_due_date(self):
        due = NOW + timedelta(days=1)
        times = reminders.task_reminders(task(due=due, templates=[
            {"value": -1, "unit": "d"}, {"value": 0, "unit": "m"}, {"value": 3, "unit": "h"},
            {"value": 2, "unit": "w"}, {"value": "x", "unit": "m"}]))
        self.assertEqual(times, [(NOW, -1440), (due, 0), (due + timedelta(hours=3), 180)])
        self.assertEqual([reminders.reminder_kind(m) for _, m in times], ["before", "due", "after"])

    def test_no_reminders_without_due_date_or_when_turned_off(self):
        self.assertEqual(reminders.task_reminders(task(due=None)), [])
        self.assertEqual(reminders.task_reminders(task(notification=False)), [])
        self.assertEqual(reminders.task_reminders(task(active=False)), [])

    def test_naive_due_dates_are_utc(self):
        naive = (NOW + timedelta(hours=2)).replace(tzinfo=None)
        self.assertEqual(reminders.task_reminders(task(due=naive))[0][0], NOW + timedelta(hours=1, minutes=30))

    def make_scheduler(self):
        self.timers, self.fired, self.cancelled = {}, [], []

        def schedule(when, action):
            self.timers[when] = action
            return lambda: self.cancelled.append(when)

        return reminders.ReminderScheduler(schedule, lambda event, data: self.fired.append((event, data)),
                                           now=lambda: NOW)

    def test_scheduler_fires_the_latest_details(self):
        scheduler = self.make_scheduler()
        scheduler.update([task(templates=[{"value": -30, "unit": "m"}, {"value": -3, "unit": "h"}])],
                         MEMBERS, "entry")
        when = NOW + timedelta(hours=1, minutes=30)
        self.assertEqual(list(self.timers), [when])  # the 3-hour reminder is already past
        scheduler.update([task(name="Vider et ranger", assigned_to=3)], MEMBERS, "entry")
        self.assertEqual(self.cancelled, [])
        self.timers[when](NOW)
        event, data = self.fired[0]
        self.assertEqual(event, reminders.EVENT_TASK_REMINDER)
        self.assertEqual((data["task_name"], data["assigned_to"], data["assigned_to_name"], data["kind"]),
                         ("Vider et ranger", 3, "anna", "before"))
        self.assertEqual(data["offset_minutes"], -30)
        self.assertEqual(data["config_entry_id"], "entry")

    def test_scheduler_cancels_reminders_that_no_longer_apply(self):
        scheduler = self.make_scheduler()
        scheduler.update([task()], MEMBERS, "entry")
        old = next(iter(self.timers))
        scheduler.update([task(due=NOW + timedelta(days=1))], MEMBERS, "entry")  # completed: next due date
        self.assertEqual(self.cancelled, [old])
        self.timers[old](NOW)  # a timer that already ran out does not fire stale details
        self.assertEqual(self.fired, [])
        scheduler.cancel_all()
        self.assertEqual(len(self.cancelled), 2)


if __name__ == "__main__":
    unittest.main()
