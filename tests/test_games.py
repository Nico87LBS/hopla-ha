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


class ChronoTests(unittest.TestCase):
    def test_a_speed_bonus_is_shown_with_who_started_it(self):
        self.assertEqual(games.chrono_attributes({"points": 5, "endsAt": "2026-10-24T16:20:00Z", "liveId": 3}),
                         {"points": 5, "ends_at": "2026-10-24T16:20:00Z", "live_id": 3})
        self.assertEqual(games.chrono_attributes({"points": 5, "endsAt": "2026-10-24T16:20:00Z"})["live_id"], None)
        self.assertIsNone(games.chrono_attributes(None))


class LedgerTests(unittest.TestCase):
    def test_entries_carry_member_names(self):
        entry = games.ledger_entries([row(4, reason="Chambre rangée")], MEMBERS)[0]
        self.assertEqual(entry["user_name"], "elena")
        self.assertEqual(entry["created_by_name"], "Nico")
        self.assertEqual(entry["reason"], "Chambre rangée")
        self.assertEqual(games.ledger_entries(None, MEMBERS), [])

    def test_a_history_page_names_each_row_and_tells_if_older_rows_remain(self):
        rows = [row(9, reason="Aide spontanée"), row(8, action="task", choreId=3),
                row(7, action="redeem", delta=-30, rewardId=5), row(6, action="undo", choreId=99)]
        tasks = [SimpleNamespace(id=3, name="Ranger sa chambre")]
        rewards = [SimpleNamespace(id=5, name="30 min de tablette")]
        page = games.history_page(rows, MEMBERS, 3, tasks, rewards)
        self.assertEqual([e["name"] for e in page["entries"]], ["Aide spontanée", "Ranger sa chambre", "30 min de tablette"])
        self.assertTrue(page["more"])
        last = games.history_page(rows[3:], MEMBERS, 3)
        self.assertEqual(last["entries"][0]["name"], "")
        self.assertFalse(last["more"])

    def test_presets_keep_their_sign(self):
        self.assertEqual(games.presets([{"id": 1, "name": "Dispute", "points": -3, "familyId": 1}]),
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
        self.assertEqual(today["surprise"], {"task_id": 12, "task_ids": [12], "task_name": "Dents", "points": 5,
                                             "day": "2026-10-21"})
        self.assertEqual(today["bonus_period"]["multiplier"], 2)
        self.assertEqual(today["streaks"][2], {"current": 4, "best": 9, "done_today": True})
        self.assertEqual(today["streak_every"], 7)
        self.assertIsNone(games.games_today(None))
        quiet = games.games_today({"surprise": None, "period": None, "streaks": None})
        self.assertIsNone(quiet["surprise"])
        self.assertEqual(quiet["streaks"], {})
        self.assertEqual(quiet["routines"], [])

    def test_routines_carry_each_child_step(self):
        today = games.games_today({"routines": [{"id": 3, "name": "Matin", "bonus": 5, "choreIds": [1, 2],
                                                 "taskIds": [1, 2, 4],
                                                 "members": [{"userId": 2, "current": 2, "step": 2, "done": 1,
                                                              "total": 2, "finished": False}]}]})
        self.assertEqual(today["routines"], [{"id": 3, "name": "Matin", "bonus": 5, "task_ids": [1, 2, 4], "members": [
            {"user_id": 2, "current": 2, "step": 2, "done": 1, "total": 2, "finished": False}]}])

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


def progress(level=1, quest_done=False, solo_winners=(), goal_done=False, total=20):
    rank = [{"name": "Petit Hop", "icon": "🐣", "minPoints": 0}, {"name": "Hop Hop", "icon": "🐸", "minPoints": 100},
            {"name": "Super Hop", "icon": "🦘", "minPoints": 300}]
    return {**TODAY,
            "ranks": [rank[2], rank[0], rank[1]],
            "members": [{"userId": 2, "earned": 120 if level == 2 else 40, "level": level, "rank": rank[level - 1],
                         "next": rank[level], "quests": [
                             {"id": 7, "name": "Mettre la table", "kind": "tasks", "choreId": 11, "period": "week",
                              "target": 5, "progress": 5 if quest_done else 3, "reward": 8,
                              "completedAt": "2026-10-21T08:00:00Z" if quest_done else None,
                              "endsAt": "2026-10-26T00:00:00+02:00"}]}],
            "challenges": [
                {"id": 1, "name": "Piscine", "kind": "points", "target": 200, "shared": True, "members": [1, 2],
                 "progress": {"1": 5, "2": total - 5}, "total": total, "reward": 0, "rewardText": "Sortie piscine",
                 "startsAt": "2026-10-20T00:00:00Z", "endsAt": "2026-10-30T00:00:00Z",
                 "completedAt": "2026-10-22T00:00:00Z" if goal_done else None, "winners": [1, 2] if goal_done else []},
                {"id": 2, "name": "Chambre", "kind": "tasks", "choreId": 10, "target": 3, "shared": False,
                 "members": [2], "progress": {"2": 1}, "total": 1, "reward": 5, "rewardText": "",
                 "targets": {"2": 2}, "daysAway": {"2": 3},
                 "startsAt": "2026-10-20T00:00:00Z", "endsAt": "2026-10-30T00:00:00Z", "completedAt": None,
                 "winners": list(solo_winners)},
            ]}


class ProgressionTests(unittest.TestCase):
    def test_shape(self):
        today = games.games_today(progress())
        self.assertEqual(today["ranks"][2], {"level": 1, "name": "Petit Hop", "icon": "🐣", "image": None, "earned": 40, "min_points": 0,
                                             "next_name": "Hop Hop", "next_icon": "🐸", "next_image": None,
                                             "next_points": 100,
                                             "stars": 0, "round_points": 40, "star_at": None})
        quest = today["quests"][2][0]
        self.assertEqual((quest["task_id"], quest["progress"], quest["target"], quest["done"]), (11, 3, 5, False))
        goal, solo = today["challenges"]
        self.assertEqual(goal["progress"], {1: 5, 2: 15})
        self.assertEqual(goal["reward_text"], "Sortie piscine")
        self.assertFalse(goal["done"])
        self.assertIsNone(solo["reward_text"])
        self.assertEqual((solo["targets"], solo["days_away"]), ({2: 2}, {2: 3}), "away 3 days: a lower target")
        self.assertEqual((goal["targets"], goal["days_away"]), ({}, {}))
        self.assertEqual([(rank["name"], rank["min_points"]) for rank in today["rank_ladder"]],
                         [("Petit Hop", 0), ("Hop Hop", 100), ("Super Hop", 300)])
        self.assertEqual(today["rank_ladder"][0], {"name": "Petit Hop", "icon": "🐣", "image": None, "min_points": 0})
        quiet = games.games_today({"rules": {}})
        self.assertEqual((quiet["ranks"], quiet["quests"], quiet["challenges"], quiet["rank_ladder"]), ({}, {}, [], []))

    def test_events(self):
        fired = []
        tracker = games.GamesTracker(lambda event, data: fired.append((event, data)))
        tracker.update(games.games_today(progress()), "entry", MEMBERS)
        tracker.update(games.games_today(progress(level=2, quest_done=True, solo_winners=[2], goal_done=True, total=200)),
                       "entry", MEMBERS)
        events = {event: data for event, data in fired}
        self.assertEqual(list(events), [games.EVENT_RANK_UP, games.EVENT_QUEST_COMPLETED, games.EVENT_CHALLENGE_WON,
                                        games.EVENT_GOAL_REACHED])
        self.assertEqual(events[games.EVENT_RANK_UP]["name"], "Hop Hop")
        self.assertEqual(events[games.EVENT_RANK_UP]["user_name"], "elena")
        self.assertEqual(events[games.EVENT_QUEST_COMPLETED]["reward"], 8)
        self.assertEqual(events[games.EVENT_CHALLENGE_WON]["name"], "Chambre")
        self.assertEqual(events[games.EVENT_GOAL_REACHED]["member_names"], ["Nico", "elena"])
        self.assertEqual(events[games.EVENT_GOAL_REACHED]["config_entry_id"], "entry")
        fired.clear()
        tracker.update(games.games_today(progress(level=2, quest_done=True, solo_winners=[2], goal_done=True, total=200)),
                       "entry", MEMBERS)
        self.assertEqual(fired, [], "each event fires once")
        self.assertFalse(events[games.EVENT_RANK_UP]["new_star"])

    def test_a_prestige_star_is_a_rank_up(self):
        fired = []
        tracker = games.GamesTracker(lambda event, data: fired.append((event, data)))
        before = progress(level=2)
        tracker.update(games.games_today(before), "entry", MEMBERS)
        after = progress()
        after["members"][0]["stars"] = 1
        tracker.update(games.games_today(after), "entry", MEMBERS)
        rank_up = [data for event, data in fired if event == games.EVENT_RANK_UP]
        self.assertEqual(len(rank_up), 1, "back to the first rank with a star is a step up")
        self.assertTrue(rank_up[0]["new_star"])
        self.assertEqual((rank_up[0]["stars"], rank_up[0]["name"]), (1, "Petit Hop"))

    def test_the_first_refresh_only_records(self):
        fired = []
        tracker = games.GamesTracker(lambda event, data: fired.append(event))
        tracker.update(games.games_today(progress(level=2, quest_done=True, goal_done=True)), "entry", MEMBERS)
        self.assertEqual(fired, [])


class NextChangeRefreshTests(unittest.TestCase):
    def setUp(self):
        self.timers = []
        self.refreshes = 0

        def schedule(when, action):
            timer = {"when": when, "action": action, "live": True}
            self.timers.append(timer)

            def cancel():
                timer["live"] = False
            return cancel

        def refresh():
            self.refreshes += 1

        self.next = games.NextChangeRefresh(schedule, refresh)

    def live(self):
        return [t for t in self.timers if t["live"]]

    def test_refreshes_a_second_after_the_next_change(self):
        self.next.update({"next_change_at": "2026-10-30T23:00:00Z"})
        self.assertEqual(len(self.live()), 1)
        self.assertEqual(self.live()[0]["when"].isoformat(), "2026-10-30T23:00:01+00:00")
        self.live()[0]["action"]()
        self.assertEqual(self.refreshes, 1)

    def test_the_same_time_is_scheduled_once_and_a_new_one_replaces_it(self):
        self.next.update({"next_change_at": "2026-10-30T23:00:00Z"})
        self.next.update({"next_change_at": "2026-10-30T23:00:00Z"})
        self.assertEqual(len(self.live()), 1)
        self.next.update({"next_change_at": "2026-10-30T15:00:00Z"})
        self.assertEqual(len(self.live()), 1)
        self.assertEqual(self.live()[0]["when"].hour, 15)

    def test_nothing_is_scheduled_without_a_time(self):
        self.next.update(None)
        self.next.update({"next_change_at": None})
        # An older Hopla sends Go's zero time.
        self.next.update({"next_change_at": "0001-01-01T00:00:00Z"})
        self.assertEqual(self.live(), [])

    def test_cancel_stops_the_timer(self):
        self.next.update({"next_change_at": "2026-10-30T23:00:00Z"})
        self.next.cancel()
        self.assertEqual(self.live(), [])

    def test_games_today_carries_the_next_change(self):
        self.assertEqual(games.games_today({"nextChangeAt": "2026-10-30T23:00:00Z"})["next_change_at"],
                         "2026-10-30T23:00:00Z")

    def test_games_today_carries_the_currency_hops_by_default(self):
        self.assertEqual(games.games_today({"currency": "carrots"})["currency"], "carrots")
        self.assertEqual(games.games_today({"surprise": None})["currency"], "hops")


if __name__ == "__main__":
    unittest.main()
