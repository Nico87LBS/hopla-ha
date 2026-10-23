"""Check that the tasks of a child who is away wait for her."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/hopla/presence.py"
spec = importlib.util.spec_from_file_location("hopla_presence", SOURCE)
presence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(presence)


def task(task_id, *members):
    return SimpleNamespace(id=task_id, members_now=list(members))


class PresenceTests(unittest.TestCase):
    def test_tasks_of_a_child_away_wait(self):
        members = [SimpleNamespace(user_id=1, away=False), SimpleNamespace(user_id=2, away=True),
                   SimpleNamespace(user_id=3, away=False)]
        tasks = [task(1, 2), task(2, 3), task(3, 2, 3), task(4), task(5, 1)]
        self.assertEqual(presence.away_ids(members), {2})
        self.assertEqual([t.id for t in presence.present_tasks(tasks, members)], [2, 3, 4, 5])

    def test_a_task_for_all_waits_when_all_are_away(self):
        members = [SimpleNamespace(user_id=2, away=True), SimpleNamespace(user_id=3, away=True)]
        self.assertEqual([t.id for t in presence.present_tasks([task(3, 2, 3), task(4)], members)], [4])

    def test_nobody_away_keeps_every_task(self):
        tasks = [task(1, 2)]
        self.assertIs(presence.present_tasks(tasks, [SimpleNamespace(user_id=2, away=False)]), tasks)


if __name__ == "__main__":
    unittest.main()
