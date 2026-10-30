"""Task sensors made before 0.25.0 get their unique id of today and keep
their entity id."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/hopla/chore_sensor.py"


class Registry:
    def __init__(self, entries):
        self.entries = entries

    def async_get_entity_id(self, domain, platform, unique_id):
        return next((e.entity_id for e in self.entries if e.unique_id == unique_id), None)

    def async_update_entity(self, entity_id, new_unique_id):
        next(e for e in self.entries if e.entity_id == entity_id).unique_id = new_unique_id


class ChoreUniqueIdTests(unittest.TestCase):
    def test_old_unique_ids_are_renamed(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        nodes = [node for node in tree.body
                 if getattr(node, "name", None) == "_rename_old_unique_ids"
                 or isinstance(node, ast.Assign) and node.targets[0].id in ("UNIQUE_ID_PREFIX", "_OLD_UNIQUE_ID_PREFIX")]
        entries = [
            SimpleNamespace(domain="sensor", entity_id="sensor.ranger", unique_id="dt_chore_e_7"),
            SimpleNamespace(domain="sensor", entity_id="sensor.dents", unique_id="hopla_chore_e_8"),
            SimpleNamespace(domain="todo", entity_id="todo.hopla", unique_id="dt_chore_e_9"),
        ]
        registry = Registry(entries)
        namespace = {"HomeAssistant": object, "ConfigEntry": object, "DOMAIN": "hopla",
                     "er": SimpleNamespace(async_get=lambda hass: registry,
                                           async_entries_for_config_entry=lambda reg, entry_id: entries)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(SOURCE), "exec"), namespace)

        namespace["_rename_old_unique_ids"](None, SimpleNamespace(entry_id="e"))

        self.assertEqual([e.unique_id for e in entries], ["hopla_chore_e_7", "hopla_chore_e_8", "dt_chore_e_9"])
        self.assertEqual(entries[0].entity_id, "sensor.ranger")
