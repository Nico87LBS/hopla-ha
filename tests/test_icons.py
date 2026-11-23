"""Icons of the Hopla catalogue on the card."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"
spec = importlib.util.spec_from_file_location("hopla_icons", ROOT / "icons.py")
icons = importlib.util.module_from_spec(spec)
spec.loader.exec_module(icons)


class ResolveTests(unittest.TestCase):
    def test_a_known_id_is_kept(self):
        self.assertEqual(icons.resolve_icon("broom", icons.TASK_DEFAULT), "broom")

    def test_an_unknown_or_missing_icon_gets_the_default_of_its_kind(self):
        self.assertEqual(icons.resolve_icon("nope", icons.TASK_DEFAULT), "task_default")
        self.assertEqual(icons.resolve_icon(None, icons.REWARD_DEFAULT), "reward_default")
        self.assertEqual(icons.resolve_icon("../x", icons.CHALLENGE_DEFAULT), "trophy")

    def test_an_older_emoji_becomes_its_icon(self):
        emoji, icon = next(iter(icons._catalogue()[1].items()))
        self.assertEqual(icons.resolve_icon(emoji, "x"), icon)

    def test_every_listed_icon_has_its_drawing_and_the_defaults_exist(self):
        ids = json.loads((ROOT / "frontend/icons/catalogue.json").read_text(encoding="utf-8"))["ids"]
        for id in ids:
            self.assertTrue((ROOT / "frontend/icons" / f"{id}.svg").is_file(), id)
        for default in (icons.TASK_DEFAULT, icons.REWARD_DEFAULT, icons.PROJECT_DEFAULT,
                        icons.ROUTINE_DEFAULT, icons.CHALLENGE_DEFAULT):
            self.assertIn(default, ids)

    def test_routines_projects_and_challenges_get_an_icon(self):
        today = {"routines": [{"icon": None}], "projects": [{"icon": "broom"}], "challenges": [{"icon": "zzz"}]}
        board = [{"icon": ""}]
        icons.with_icons(today, board)
        self.assertEqual([today["routines"][0]["icon"], today["projects"][0]["icon"], today["challenges"][0]["icon"], board[0]["icon"]],
                         ["routine_default", "broom", "trophy", "trophy"])
        icons.with_icons(None, None)


if __name__ == "__main__":
    unittest.main()
