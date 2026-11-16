"""Rated challenges: what the sensor shows, and the events for a parent to validate."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"
spec = importlib.util.spec_from_file_location("hopla_games", ROOT / "games.py")
games = importlib.util.module_from_spec(spec)
spec.loader.exec_module(games)

LEVELS = [{"key": "jaune", "name": "Jaune", "color": "#E0B000", "position": 0},
          {"key": "vert", "name": "Vert", "color": "#17A34A", "position": 1}]
MEMBERS = [SimpleNamespace(user_id=2, display_name="Elena", username="elena")]


def challenge(**extra):
    return {"id": 7, "name": "Dictées", "status": "running", "endsAt": "2099-01-01T00:00:00Z",
            "occurrence": {"id": 11}, "goal": {"id": 5, "type": "levels", "unit": ""}, "levels": LEVELS,
            "milestones": [{"id": 1}, {"id": 2}], "members": [], **extra}


class RatedChallengeTests(unittest.TestCase):
    def test_only_running_challenges_are_shown(self):
        board = {"challenges": [challenge(), challenge(id=8, status="upcoming"), challenge(id=9, occurrence=None)]}
        self.assertEqual([c["id"] for c in games.rated_challenges(board)], [7])
        self.assertEqual(games.rated_challenges(None), [])

    def test_a_member_stands_on_the_best_validated_level(self):
        member = {"userId": 2, "hops": 5, "awardedMilestoneIds": [1], "results": [
            {"id": 1, "status": "approved", "levelKey": "vert"}, {"id": 2, "status": "approved", "levelKey": "jaune"}]}
        shown = games.rated_challenges({"challenges": [challenge(members=[member])]})[0]
        self.assertEqual(shown["occurrence_id"], 11)
        self.assertEqual(shown["goal_id"], 5)
        self.assertEqual(shown["members"][0], {"id": 2, "state": "todo", "best": 1, "hops": 5,
                                                "result_id": None, "result_text": None})

    def test_a_result_waiting_for_a_parent_puts_the_member_in_validation(self):
        member = {"userId": 2, "results": [{"id": 41, "status": "pending", "levelKey": "vert"}]}
        shown = games.rated_challenges({"challenges": [challenge(members=[member])]})[0]["members"][0]
        self.assertEqual((shown["state"], shown["result_id"], shown["result_text"]), ("pending", 41, "Vert"))

    def test_reaching_the_last_milestone_is_done(self):
        member = {"userId": 2, "awardedMilestoneIds": [1, 2], "results": []}
        self.assertEqual(games.rated_challenges({"challenges": [challenge(members=[member])]})[0]["members"][0]["state"], "done")

    def test_a_number_challenge_keeps_the_highest_value(self):
        number = challenge(goal={"id": 6, "type": "result", "unit": "/20", "targetValue": 18}, levels=[], members=[
            {"userId": 2, "results": [{"id": 1, "status": "approved", "value": 12.0}, {"id": 2, "status": "pending", "value": 15.5}]}])
        shown = games.rated_challenges({"challenges": [number]})[0]
        self.assertEqual((shown["kind"], shown["unit"]), ("value", "/20"))
        self.assertEqual(shown["members"][0]["best"], 12.0)
        self.assertEqual(shown["members"][0]["result_text"], "15.5 /20")


class ResultNotificationTests(unittest.TestCase):
    def test_a_parent_is_told_once_and_the_notification_is_cleared_when_answered(self):
        fired = []
        tracker = games.ChallengeResultTracker(lambda event, data: fired.append((event, data)))
        board = {"challenges": [challenge()], "pending": [{"id": 41, "userId": 2, "challengeId": 7,
                 "challengeName": "Dictées", "levelKey": "vert"}]}
        pending = games.pending_results(board, MEMBERS)
        tracker.update([], "entry")          # a restart records the state without notifying
        tracker.update(pending, "entry")
        tracker.update(pending, "entry")
        self.assertEqual([event for event, _ in fired], [games.EVENT_CHALLENGE_RESULT_PENDING])
        self.assertEqual(fired[0][1]["user_name"], "Elena")
        self.assertEqual(fired[0][1]["text"], "Vert")
        tracker.update([], "entry")
        self.assertEqual(fired[-1][0], games.EVENT_CHALLENGE_RESULT_RESOLVED)
        self.assertEqual(fired[-1][1]["result_id"], 41)


if __name__ == "__main__":
    unittest.main()
