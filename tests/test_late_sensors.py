"""Sensors whose data arrives after setup are added on a later refresh."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"
tree = ast.parse((ROOT / "family_sensor.py").read_text(encoding="utf-8"))
setup = next(node for node in tree.body if getattr(node, "name", None) == "async_setup_family_sensors")


class Sensor:
    def __init__(self, coordinator, entry, user_id=None):
        self.user_id = user_id


def sensor_class(name):
    return type(name, (Sensor,), {})


class Coordinator:
    def __init__(self):
        self.rewards = None
        self.points_presets = None
        self.games_today = None
        self.listeners = []

    def async_add_listener(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def refresh(self):
        for listener in list(self.listeners):
            listener()


class LateSensorTests(unittest.TestCase):
    def setUp(self):
        self.namespace = {
            "DOMAIN": "hopla", "callback": lambda f: f, "SensorEntity": object, "HoplaMember": object,
            "HomeAssistant": object, "ConfigEntry": object, "AddEntitiesCallback": object,
            **{name: sensor_class(name) for name in ("HoplaPendingApprovalSensor", "HoplaRewardsSensor",
                                                     "HoplaBonusSensor", "HoplaGamesSensor", "HoplaPointsSensor")},
        }
        exec(compile(ast.Module(body=[setup], type_ignores=[]), "family_sensor", "exec"), self.namespace)

    def run_setup(self, coordinator, members):
        added = []
        entry = SimpleNamespace(entry_id="e", async_on_unload=lambda f: None)
        hass = SimpleNamespace(data={"hopla": {"e": {"coordinator": coordinator, "family_members": members}}})
        asyncio.run(self.namespace["async_setup_family_sensors"](
            hass, entry, lambda entities: added.extend(type(e).__name__ for e in entities)))
        return added

    def test_games_sensor_added_when_games_arrive_later(self):
        coordinator = Coordinator()
        coordinator.rewards = []
        members = [SimpleNamespace(user_id=2, is_active=True)]
        added = self.run_setup(coordinator, members)
        self.assertEqual(sorted(added), ["HoplaPendingApprovalSensor", "HoplaPointsSensor", "HoplaRewardsSensor"])
        added.clear()
        coordinator.refresh()
        self.assertEqual(added, [], "nothing new without games data")
        coordinator.games_today = {"streaks": {}}
        coordinator.refresh()
        coordinator.refresh()
        self.assertEqual(added, ["HoplaGamesSensor"], "added once")


if __name__ == "__main__":
    unittest.main()
