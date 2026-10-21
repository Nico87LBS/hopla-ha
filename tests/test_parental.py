"""Parent accounts, the parent code and reward requests from the family tablet."""
import ast
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"
spec = importlib.util.spec_from_file_location("hopla_parental", ROOT / "parental.py")
parental = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parental)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 21, 18, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def guard(clock, users=("nico",), pin="2468", changes=None):
    pin_hash, salt = parental.hash_pin(pin) if pin else (None, None)
    return parental.ParentGuard(users, pin_hash, salt, now=clock,
                                on_change=(lambda: changes.append(clock())) if changes is not None else None)


class ParentGuardTests(unittest.TestCase):
    def test_without_parents_everyone_keeps_full_access(self):
        self.assertTrue(parental.ParentGuard().is_parent("tablette"))

    def test_parents_and_automations_pass_and_the_tablet_does_not(self):
        g = guard(Clock())
        self.assertTrue(g.is_parent("nico"))
        self.assertTrue(g.is_parent(None))
        self.assertFalse(g.is_parent("tablette"))
        with self.assertRaises(parental.ParentModeError) as err:
            g.require_parent("tablette")
        self.assertEqual(err.exception.reason, "parent_required")

    def test_code_opens_parent_mode_for_two_minutes(self):
        clock, changes = Clock(), []
        g = guard(clock, changes=changes)
        until = g.unlock("2468")
        self.assertEqual(until, clock.now + timedelta(minutes=2))
        self.assertTrue(g.is_parent("tablette"))
        clock.now += timedelta(minutes=1, seconds=59)
        self.assertTrue(g.is_parent("tablette"))
        clock.now += timedelta(seconds=2)
        self.assertFalse(g.is_parent("tablette"))
        g.expire()
        self.assertIsNone(g.unlocked_until)
        self.assertEqual(len(changes), 2, "opening and closing both update the entities")

    def test_lock_closes_parent_mode_early(self):
        g = guard(Clock())
        g.unlock("2468")
        g.lock()
        self.assertFalse(g.is_parent("tablette"))

    def test_wrong_codes_count_down_then_lock_out(self):
        clock = Clock()
        g = guard(clock)
        for left in (4, 3, 2, 1):
            with self.assertRaises(parental.ParentModeError) as err:
                g.unlock("1111")
            self.assertEqual((err.exception.reason, err.exception.details["attempts_left"]), ("pin_wrong", left))
        with self.assertRaises(parental.ParentModeError) as err:
            g.unlock("abcd")
        self.assertEqual(err.exception.reason, "pin_locked")
        with self.assertRaises(parental.ParentModeError) as err:
            g.unlock("2468")
        self.assertEqual(err.exception.reason, "pin_locked", "even the right code waits for the lockout")
        clock.now += timedelta(minutes=5)
        g.unlock("2468")
        self.assertTrue(g.unlocked)

    def test_no_code_means_no_parent_mode(self):
        with self.assertRaises(parental.ParentModeError) as err:
            guard(Clock(), pin=None).unlock("2468")
        self.assertEqual(err.exception.reason, "pin_not_set")

    def test_code_format_and_hash(self):
        self.assertTrue(parental.valid_pin("0123"))
        for pin in ("123", "12345", "12a4", 1234, None):
            self.assertFalse(parental.valid_pin(pin))
        pin_hash, salt = parental.hash_pin("2468")
        self.assertNotIn("2468", pin_hash)
        self.assertEqual(parental.hash_pin("2468", salt)[0], pin_hash)
        self.assertNotEqual(parental.hash_pin("2468")[1], salt, "each code gets its own salt")


class RewardRequestTests(unittest.TestCase):
    def redemption(self, rid, status=0, user=2):
        return SimpleNamespace(id=rid, reward_id=7, reward_name="Écran", points_cost=10, user_id=user, status=status,
                               requested_at=datetime(2026, 10, 21, 17, tzinfo=timezone.utc))

    def test_pending_requests_name_the_member(self):
        members = [SimpleNamespace(user_id=2, display_name="Elena", username="elena")]
        pending = parental.pending_rewards([self.redemption(1), self.redemption(2, status=1)], members)
        self.assertEqual(pending, [{"redemption_id": 1, "reward_id": 7, "reward_name": "Écran", "points_cost": 10,
                                    "user_id": 2, "user_name": "Elena", "requested_at": "2026-10-21T17:00:00+00:00"}])

    def test_tracker_announces_new_and_answered_requests_only(self):
        fired = []
        tracker = parental.RewardRequestTracker(lambda event, data: fired.append((event, data)))
        item = {"redemption_id": 1, "reward_name": "Écran", "user_id": 2}
        tracker.update([item], "entry")
        self.assertEqual(fired, [], "requests already waiting at start are not announced again")
        second = {"redemption_id": 2, "reward_name": "Glace", "user_id": 3}
        tracker.update([item, second], "entry")
        tracker.update([second], "entry")
        self.assertEqual(fired, [
            (parental.EVENT_REWARD_REQUESTED, {**second, "config_entry_id": "entry"}),
            (parental.EVENT_REWARD_REQUEST_RESOLVED, {"redemption_id": 1, "reward_name": "Écran", "user_id": 2,
                                                      "config_entry_id": "entry"}),
        ])


class RedeemServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8"))
        wanted = {"async_redeem_reward_service", "_get_config", "require_parent", "_parent_error"}
        functions = [node for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted]
        self.calls = []

        async def resolve(hass, entry_id):
            return SimpleNamespace(entry_id="entry")

        async def redeem(reward_id, user_id, request=False):
            self.calls.append((reward_id, user_id, request))
            return SimpleNamespace(id=5, status=0 if request else 1, points_cost=10)

        async def refresh():
            pass

        class Refused(Exception):
            def __init__(self, **kwargs):
                super().__init__(kwargs["translation_key"])

        namespace = {"HomeAssistant": object, "ServiceCall": object, "ServiceResponse": dict, "DOMAIN": "hopla",
                     "HomeAssistantError": RuntimeError, "ServiceValidationError": Refused,
                     "ParentModeError": parental.ParentModeError, "_get_config_entry": resolve,
                     "dt_util": SimpleNamespace(utcnow=lambda: datetime.now(timezone.utc))}
        exec(compile(ast.Module(body=functions, type_ignores=[]), "services", "exec"), namespace)
        self.namespace = namespace
        self.config = {"client": SimpleNamespace(async_redeem_reward=redeem),
                       "coordinator": SimpleNamespace(async_refresh=refresh),
                       "parental": guard(Clock())}
        self.hass = SimpleNamespace(data={"hopla": {"entry": self.config}})

    def call(self, user_id):
        return SimpleNamespace(data={"reward_id": 7, "user_id": 2}, context=SimpleNamespace(user_id=user_id))

    async def test_parent_redeems_at_once_and_tablet_sends_a_request(self):
        redeem = self.namespace["async_redeem_reward_service"]
        self.assertEqual((await redeem(self.hass, self.call("nico")))["approved"], True)
        response = await redeem(self.hass, self.call("tablette"))
        self.assertEqual((response["approved"], response["pending"]), (False, True))
        self.assertEqual(self.calls, [(7, 2, False), (7, 2, True)])

    def test_tablet_is_refused_parent_actions(self):
        with self.assertRaises(Exception) as err:
            self.namespace["require_parent"](self.config, self.call("tablette"))
        self.assertEqual(str(err.exception), "parent_required")
        self.namespace["require_parent"](self.config, self.call("nico"))


if __name__ == "__main__":
    unittest.main()
