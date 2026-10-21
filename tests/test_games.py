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


TODAY = {
    "rules": {"streakEvery": 7, "streakBonus": 10},
    "surprise": {"choreId": 12, "name": "Dents", "points": 5, "day": "2026-10-21"},
    "period": {"id": 1, "name": "Week-end double", "multiplier": 2,
               "startsAt": "2026-10-21T00:00:00Z", "endsAt": "2026-10-23T00:00:00Z"},
    "streaks": [{"userId": 2, "current": 4, "best": 9, "doneToday": True}],
}


class GamesTodayTests(unittest.TestCase):
    def test_shape(self):
        today = games.games_today(TODAY)
        self.assertEqual(today["surprise"], {"task_id": 12, "task_name": "Dents", "points": 5, "day": "2026-10-21"})
        self.assertEqual(today["bonus_period"]["multiplier"], 2)
        self.assertEqual(today["streaks"][2], {"current": 4, "best": 9, "done_today": True})
        self.assertEqual(today["streak_every"], 7)
        self.assertIsNone(games.games_today(None))
        quiet = games.games_today({"surprise": None, "period": None, "streaks": None})
        self.assertIsNone(quiet["surprise"])
        self.assertEqual(quiet["streaks"], {})

    def test_events_for_a_new_surprise_and_periods_starting_and_ending(self):
        fired = []
        tracker = games.GamesTracker(lambda event, data: fired.append((event, data)))
        tracker.update(games.games_today(TODAY), "entry")
        self.assertEqual(fired, [], "the first refresh only records")
        tracker.update(games.games_today(TODAY), "entry")
        self.assertEqual(fired, [])
        tomorrow = {**TODAY, "surprise": {**TODAY["surprise"], "day": "2026-10-22", "choreId": 11}, "period": None}
        tracker.update(games.games_today(tomorrow), "entry")
        self.assertEqual([event for event, _ in fired], [games.EVENT_SURPRISE_TASK, games.EVENT_BONUS_PERIOD_ENDED])
        self.assertEqual(fired[0][1]["task_id"], 11)
        self.assertEqual(fired[1][1]["name"], "Week-end double")
        fired.clear()
        tracker.update(games.games_today({**tomorrow, "period": {**TODAY["period"], "id": 2}}), "entry")
        self.assertEqual([event for event, _ in fired], [games.EVENT_BONUS_PERIOD_STARTED])
        self.assertEqual(fired[0][1]["config_entry_id"], "entry")


if __name__ == "__main__":
    unittest.main()
