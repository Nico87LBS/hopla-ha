"""Bonuses, penalties and the points ledger events."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"
spec = importlib.util.spec_from_file_location("hopla_games", ROOT / "games.py")
games = importlib.util.module_from_spec(spec)
spec.loader.exec_module(games)

MEMBERS = [SimpleNamespace(user_id=1, display_name="Nico", username="nico"),
           SimpleNamespace(user_id=2, display_name="", username="elena")]


def row(id, action="bonus", points=5, delta=5, user=2, **extra):
    return {"id": id, "userId": user, "action": action, "points": points, "delta": delta,
            "createdBy": 1, "createdAt": "2026-10-21T08:00:00Z", **extra}


class LedgerTests(unittest.TestCase):
    def test_entries_carry_member_names(self):
        entry = games.ledger_entries([row(4, reason="Chambre rangée")], MEMBERS)[0]
        self.assertEqual(entry["user_name"], "elena")
        self.assertEqual(entry["created_by_name"], "Nico")
        self.assertEqual(entry["reason"], "Chambre rangée")
        self.assertEqual(games.ledger_entries(None, MEMBERS), [])

    def test_presets_keep_their_sign(self):
        self.assertEqual(games.presets([{"id": 1, "name": "Dispute", "points": -3, "circleId": 1}]),
                         [{"id": 1, "name": "Dispute", "points": -3}])

    def test_first_refresh_is_quiet_then_new_rows_fire_oldest_first(self):
        fired = []
        tracker = games.PointsLedgerTracker(lambda event, data: fired.append((event, data)))
        tracker.update(games.ledger_entries([row(3), row(2)], MEMBERS), "entry")
        self.assertEqual(fired, [])
        rows = [row(6, "penalty", 3, -3), row(5), row(3), row(2)]
        tracker.update(games.ledger_entries(rows, MEMBERS), "entry")
        self.assertEqual([data["id"] for _, data in fired], [5, 6])
        self.assertEqual(fired[1][0], games.EVENT_POINTS_CHANGED)
        self.assertEqual(fired[1][1]["delta"], -3)
        self.assertEqual(fired[1][1]["config_entry_id"], "entry")
        tracker.update(games.ledger_entries(rows, MEMBERS), "entry")
        self.assertEqual(len(fired), 2, "nothing new, nothing fired")

    def test_an_empty_ledger_then_a_first_row(self):
        fired = []
        tracker = games.PointsLedgerTracker(lambda event, data: fired.append(data))
        tracker.update([], "entry")
        tracker.update(games.ledger_entries([row(1)], MEMBERS), "entry")
        self.assertEqual([data["id"] for data in fired], [1])


if __name__ == "__main__":
    unittest.main()
