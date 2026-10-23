"""Approval tracking and member photos, without a Home Assistant installation."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"
spec = importlib.util.spec_from_file_location("approval", ROOT / "approval.py")
approval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(approval)

tree = ast.parse((ROOT / "family_sensor.py").read_text(encoding="utf-8"))
picture = next(node for node in tree.body if getattr(node, "name", None) == "member_picture")
namespace = {}
exec(compile(ast.Module(body=[picture], type_ignores=[]), "family_sensor", "exec"), namespace)
member_picture = namespace["member_picture"]


def task(id, status, name="Task", active=True, points=2, slots=None):
    return SimpleNamespace(id=id, status=status, name=name, is_active=active, points=points, slots_today=slots)


MEMBERS = [SimpleNamespace(user_id=2, display_name="Elena", username="nico_elena"),
           SimpleNamespace(user_id=3, display_name="", username="nico_anna")]


class ApprovalTests(unittest.TestCase):
    def test_pending_tasks_name_their_completer(self):
        history = [SimpleNamespace(chore_id=10, status=3, completed_by=2),
                   SimpleNamespace(chore_id=10, status=1, completed_by=3),
                   SimpleNamespace(chore_id=11, status=3, completed_by=3)]
        pending = approval.pending_approvals(
            [task(10, 3, "Ranger"), task(11, 3, "Table"), task(12, 0), task(13, 3, active=False)], history, MEMBERS)
        self.assertEqual([(p["task_id"], p["completed_by"], p["completed_by_name"]) for p in pending],
                         [(10, 2, "Elena"), (11, 3, "nico_anna")])

    def test_completer_unknown_outside_history_window(self):
        pending = approval.pending_approvals([task(10, 3)], [], MEMBERS)
        self.assertIsNone(pending[0]["completed_by"])
        self.assertIsNone(pending[0]["completed_by_name"])

    def test_each_slot_waits_on_its_own(self):
        slots = [{"index": 0, "name": "Matin", "state": "pending", "completedBy": 2},
                 {"index": 1, "name": "", "time": "19:30", "state": "pending", "completedBy": 2},
                 {"index": 2, "name": "Nuit", "state": "done", "completedBy": 2}]
        pending = approval.pending_approvals([task(10, 0, "Dents", slots=slots)], [], MEMBERS)
        self.assertEqual([(p["slot"], p["slot_name"], p["completed_by_name"]) for p in pending],
                         [(0, "Matin", "Elena"), (1, "19:30", "Elena")])
        fired = []
        tracker = approval.ApprovalTracker(lambda event, data: fired.append((event, data.get("slot"))))
        tracker.update(pending, "entry")
        tracker.update(pending[1:], "entry")
        self.assertEqual(fired, [(approval.EVENT_APPROVAL_RESOLVED, 0)])

    def test_tracker_fires_on_changes_only(self):
        fired = []
        tracker = approval.ApprovalTracker(lambda event, data: fired.append((event, data["task_id"])))
        item = {"task_id": 10, "task_name": "Ranger"}
        tracker.update([item], "entry")  # state at startup is not announced
        tracker.update([item], "entry")
        self.assertEqual(fired, [])
        tracker.update([], "entry")
        tracker.update([item], "entry")
        self.assertEqual(fired, [(approval.EVENT_APPROVAL_RESOLVED, 10), (approval.EVENT_PENDING_APPROVAL, 10)])


class MemberPictureTests(unittest.TestCase):
    def test_local_paths_become_public_asset_urls(self):
        self.assertEqual(member_picture("https://dt.example/", "profiles/2/a.jpg"),
                         "https://dt.example/api/v1/assets/profiles/2/a.jpg")

    def test_absolute_urls_and_missing_photos(self):
        self.assertEqual(member_picture("https://dt.example", "https://cdn/p.png"), "https://cdn/p.png")
        self.assertIsNone(member_picture("https://dt.example", ""))
        self.assertIsNone(member_picture("https://dt.example", None))


if __name__ == "__main__":
    unittest.main()
