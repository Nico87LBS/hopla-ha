"""Check task metadata parsing and sensor exposure without an HA installation."""
import ast
from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional
import unittest


ROOT = Path(__file__).resolve().parents[1] / "custom_components/hopla"


def load_definitions(filename, names, namespace):
    source = ROOT / filename
    tree = ast.parse(source.read_text(encoding="utf-8"))
    definitions = [node for node in tree.body if getattr(node, "name", None) in names]
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *definitions], type_ignores=[]))
    exec(compile(module, str(source), "exec"), namespace)


class CoordinatorStub:
    def __init__(self, coordinator):
        self.coordinator = coordinator


class TaskSensorAttributeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = dict(dataclass=dataclass, datetime=datetime, Any=Any, List=List,
                         Optional=Optional, _LOGGER=logging.getLogger(__name__),
                         CoordinatorEntity=CoordinatorStub, SensorEntity=type("SensorStub", (), {}),
                         STATUS_PENDING_APPROVAL=3)
        load_definitions("model.py", {"_parse_datetime", "HoplaTask"}, namespace)
        load_definitions("approval.py", {"slot_attributes"}, namespace)
        load_definitions("chore_sensor.py", {"HoplaChoreSensor"}, namespace)
        cls.task_class = namespace["HoplaTask"]
        cls.sensor_class = namespace["HoplaChoreSensor"]

    def attributes(self, **fields):
        task = self.task_class.from_json({"id": 1, "name": "Maintenance", **fields})
        sensor = self.sensor_class(SimpleNamespace(data=[task]), SimpleNamespace(entry_id="test"), task.id)
        return sensor.extra_state_attributes

    def test_points_preserve_zero_and_unset_values(self):
        for value in (10, 0, None):
            with self.subTest(value=value):
                self.assertEqual(self.attributes(points=value)["points"], value)
        self.assertIsNone(self.attributes()["points"])

    def test_interval_units_accompany_existing_frequency(self):
        for unit in ("hours", "days", "weeks", "months", "years"):
            with self.subTest(unit=unit):
                attrs = self.attributes(frequencyType="interval", frequency=6,
                                        frequencyMetadata={"unit": unit})
                self.assertEqual(attrs["interval_type"], unit)
                self.assertEqual(attrs["frequency"], 6)
                self.assertEqual(attrs["frequency_type"], "interval")

    def test_missing_or_invalid_interval_metadata(self):
        for metadata in (None, {}, "weeks", [], {"unit": None}, {"unit": 6}, {"unit": ""}):
            with self.subTest(metadata=metadata):
                self.assertIsNone(self.attributes(frequencyType="interval",
                                                 frequencyMetadata=metadata)["interval_type"])

    def test_other_schedules_do_not_expose_stale_interval_units(self):
        for schedule in ("once", "daily", "weekly", "trigger"):
            with self.subTest(schedule=schedule):
                self.assertIsNone(self.attributes(frequencyType=schedule,
                                                 frequencyMetadata={"unit": "weeks"})["interval_type"])

    def test_approval_status_and_assignees(self):
        attrs = self.attributes(status=3, assignees=[{"userId": 2}, {"userId": 3}])
        self.assertTrue(attrs["pending_approval"])
        self.assertEqual(attrs["status"], 3)
        self.assertEqual(attrs["assignee_ids"], [2, 3])
        attrs = self.attributes()
        self.assertFalse(attrs["pending_approval"])
        self.assertEqual(attrs["assignee_ids"], [])

    def test_slots_of_today(self):
        slots = [{"index": 0, "name": "Matin", "time": "07:30", "at": "2026-10-23T07:30:00+02:00",
                  "opensAt": "2026-10-23T06:30:00+02:00", "closesAt": "2026-10-23T11:30:00+02:00",
                  "state": "done", "historyId": 4, "completedBy": 2},
                 {"index": 1, "name": "Soir", "time": "19:30", "at": "2026-10-23T19:30:00+02:00",
                  "opensAt": "2026-10-23T18:30:00+02:00", "closesAt": "2026-10-24T00:00:00+02:00",
                  "state": "pending", "completedBy": 2}]
        attrs = self.attributes(frequencyType="daily", slotsToday=slots,
                                frequencyMetadata={"slots": [{"name": "Matin", "time": "07:30"}]})
        self.assertEqual([(s["name"], s["state"], s["completed_by"]) for s in attrs["slots_today"]],
                         [("Matin", "done", 2), ("Soir", "pending", 2)])
        self.assertEqual(attrs["slots_today"][1]["closes_at"], "2026-10-24T00:00:00+02:00")
        self.assertTrue(attrs["pending_approval"], "a slot waiting for a parent")
        self.assertEqual(self.attributes()["slots_today"], [])


if __name__ == "__main__":
    unittest.main()
