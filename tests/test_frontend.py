"""Regression checks for the bundled frontend lifecycle."""
import ast
import asyncio
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import unittest.mock
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]


class FrontendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = ROOT / "custom_components/hopla/frontend.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body
                     if not isinstance(node, (ast.Import, ast.ImportFrom))]
        self.add_url = Mock()
        namespace = {"__file__": str(source), "asyncio": asyncio,
                     "sha256": sha256, "Path": Path, "HomeAssistant": object,
                     "StaticPathConfig": lambda *args: args,
                     "add_extra_js_url": self.add_url}
        exec(compile(tree, str(source), "exec"), namespace)
        self.setup_frontend = namespace["async_setup_frontend"]
        self.card_file = namespace["CARD_FILE"]
        self.family_card_file = namespace["FAMILY_CARD_FILE"]
        self.version = namespace["frontend_version"]

        async def executor(fn):
            await asyncio.sleep(0)
            return fn()

        self.hass = SimpleNamespace(data={}, async_add_executor_job=executor,
                                    http=SimpleNamespace(async_register_static_paths=AsyncMock()))

    async def test_concurrent_entries_and_reload_register_only_once(self):
        await asyncio.gather(self.setup_frontend(self.hass), self.setup_frontend(self.hass))
        await self.setup_frontend(self.hass)
        frontend = self.card_file.parent
        self.hass.http.async_register_static_paths.assert_awaited_once_with([
            ("/hopla/hopla-user-todo-card.js", str(self.card_file), False),
            ("/hopla/hopla-family-card.js", str(self.family_card_file), False),
            ("/hopla/hopla-i18n.js", str(frontend / "hopla-i18n.js"), False),
            ("/hopla/locales", str(frontend / "locales"), False),
        ("/hopla/ranks", str(frontend / "ranks"), False)])
        version = self.version()
        self.assertEqual(self.add_url.call_args_list, [
            unittest.mock.call(self.hass, f"/hopla/hopla-user-todo-card.js?v={version}"),
            unittest.mock.call(self.hass, f"/hopla/hopla-family-card.js?v={version}")])

    async def test_translation_change_changes_version(self):
        before = self.version()
        locale = self.card_file.parent / "locales" / "fr.js"
        original = locale.read_bytes()
        try:
            locale.write_bytes(original + b"\n")
            self.assertNotEqual(self.version(), before)
        finally:
            locale.write_bytes(original)

    async def test_registration_failure_can_retry(self):
        self.hass.http.async_register_static_paths.side_effect = RuntimeError("Not ready")
        with self.assertRaises(RuntimeError):
            await self.setup_frontend(self.hass)
        self.add_url.assert_not_called()
        self.hass.http.async_register_static_paths.side_effect = None
        await self.setup_frontend(self.hass)
        self.assertEqual(self.add_url.call_count, 2)

    async def test_hacs_package_contains_card_and_setup_dependency(self):
        manifest = json.loads((ROOT / "custom_components/hopla/manifest.json").read_text())
        self.assertIn("frontend", manifest["dependencies"])
        self.assertTrue(self.card_file.is_file())
        self.assertIn("hopla-user-todo-card", self.card_file.read_text(encoding="utf-8"))
        self.assertIn("hopla-family-card", self.family_card_file.read_text(encoding="utf-8"))
        tree = ast.parse((ROOT / "custom_components/hopla/__init__.py").read_text())
        setup = next(node for node in tree.body
                     if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_setup_entry")
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id == "async_setup_frontend" for node in ast.walk(setup)))
