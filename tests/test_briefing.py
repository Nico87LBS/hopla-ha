"""The morning briefing lists today's open tasks that nothing else announces."""
import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

spec = importlib.util.spec_from_file_location("briefing", Path(__file__).resolve().parents[1] / "custom_components/hopla/briefing.py")
briefing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(briefing)

TODAY = date(2026, 11, 28)
NAMES = {1: "Elena", 2: "Anna"}


def task(id, name, members=(), due=datetime(2026, 11, 28, 6, 0, tzinfo=timezone.utc), **extra):
    base = dict(id=id, name=name, points=3, is_active=True, next_due_date=due, status=0, slots_today=[],
                frequency_metadata={}, deadline=None, notification=False, reminder_templates=[],
                members_now=list(members))
    return NS(**{**base, **extra})


def run(tasks, members=()):
    return briefing.briefing_tasks(tasks, NAMES, TODAY, timezone.utc, members)


class BriefingTest(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(briefing.parse_time("07:30"), (7, 30))
        self.assertIsNone(briefing.parse_time(""))
        self.assertIsNone(briefing.parse_time("25:00"))
        self.assertIsNone(briefing.parse_time("matin"))

    def test_lists_open_tasks_without_an_hour_by_person(self):
        result = run([task(1, "Ranger", [1]), task(2, "Vaisselle", [1, 2]), task(3, "Poubelles")])
        self.assertEqual(result["count"], 3)
        self.assertEqual({m["name"]: m["tasks"] for m in result["members"]},
                         {"Elena": ["Ranger", "Vaisselle"], "Anna": ["Vaisselle"]})
        self.assertEqual(result["unassigned"], ["Poubelles"])

    def test_leaves_out_what_something_else_announces(self):
        timed = [task(1, "Moments", [1], slots_today=[{"state": "open"}]), task(2, "Délai", [1], deadline=datetime.now()),
                 task(3, "Rappel", [1], notification=True, reminder_templates=[{"value": -5, "unit": "m"}]),
                 task(4, "Demain", [1], due=datetime(2026, 11, 29, 6, tzinfo=timezone.utc)),
                 task(5, "Inactive", [1], is_active=False), task(6, "Attente", [1], status=3)]
        self.assertEqual(run(timed)["count"], 0)

    def test_late_tasks_are_flagged(self):
        result = run([task(1, "Hier", [1], due=datetime(2026, 11, 27, 6, tzinfo=timezone.utc))])
        self.assertTrue(result["tasks"][0]["late"])

    def test_people_filter_one_several_nobody_or_a_mix(self):
        tasks = [task(1, "Elena seule", [1]), task(2, "Anna seule", [2]), task(3, "Personne")]
        names = lambda members: sorted(t["name"] for t in run(tasks, members)["tasks"])
        self.assertEqual(names([]), ["Anna seule", "Elena seule", "Personne"])
        self.assertEqual(names(["1"]), ["Elena seule"])
        self.assertEqual(names([1, "2"]), ["Anna seule", "Elena seule"])
        self.assertEqual(names(["none"]), ["Personne"])
        self.assertEqual(names(["2", "none"]), ["Anna seule", "Personne"])

    def test_filter_keeps_only_the_chosen_people_of_a_shared_task(self):
        result = run([task(1, "Vaisselle", [1, 2])], ["2"])
        self.assertEqual([m["name"] for m in result["members"]], ["Anna"])


if __name__ == "__main__":
    unittest.main()
