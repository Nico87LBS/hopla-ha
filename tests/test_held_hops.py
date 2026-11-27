"""Hops kept back for a parent are added up per member."""
import unittest
from types import SimpleNamespace as NS

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("approval", Path(__file__).resolve().parents[1] / "custom_components/hopla/approval.py")
approval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(approval)
held_hops = approval.held_hops


def entry(chore_id, by, held=True, status=1):
    return NS(chore_id=chore_id, completed_by=by, points_held=held, status=status)


class HeldHopsTest(unittest.TestCase):
    def test_sum_per_member(self):
        tasks = [NS(id=1, points=2), NS(id=2, points=10)]
        history = [entry(1, 7), entry(1, 7), entry(2, 8), entry(2, 7, held=False), entry(2, 7, status=2)]
        self.assertEqual(held_hops(tasks, history), {7: 4, 8: 10})

    def test_unknown_or_free_tasks_count_for_nothing(self):
        self.assertEqual(held_hops([NS(id=1, points=0)], [entry(1, 7), entry(9, 7)]), {})


if __name__ == "__main__":
    unittest.main()
