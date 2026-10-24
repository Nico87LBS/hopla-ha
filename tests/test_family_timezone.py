"""The family's time zone: read from the server, moved by a parent."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest


class HttpError(Exception):
    pass


class Response:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.body

    def raise_for_status(self):
        if self.status >= 400:
            raise HttpError(str(self.status))


class FamilyTimezoneApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "custom_components/hopla/api.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        client = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        client.body = [node for node in client.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name in ("__init__", "_headers", "_post_action",
                                         "async_get_family_timezone", "async_set_family_timezone")]
        future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        module = ast.fix_missing_locations(ast.Module(body=[future, client], type_ignores=[]))
        namespace = {"aiohttp": SimpleNamespace(ClientError=HttpError), "API_TIMEOUT": 10, "Optional": object,
                     "_LOGGER": logging.getLogger(__name__)}
        exec(compile(module, str(source), "exec"), namespace)
        self.client_type = namespace["HoplaApiClient"]

    def client(self, response, calls):
        def request(method, url, **kwargs):
            calls.append((method, url, kwargs.get("json")))
            return response
        session = SimpleNamespace(get=lambda url, **kwargs: request("GET", url, **kwargs), request=request)
        return self.client_type("https://hopla.invalid", "token", session)

    async def test_reads_the_family_zone(self):
        calls = []
        zone = {"timezone": "Europe/Lisbon", "server": "Europe/Paris", "custom": True}
        self.assertEqual(await self.client(Response({"res": zone}), calls).async_get_family_timezone(), zone)
        self.assertEqual(calls, [("GET", "https://hopla.invalid/eapi/v1/circle/timezone", None)])

    async def test_an_older_server_has_no_family_zone(self):
        self.assertIsNone(await self.client(Response({}, status=404), []).async_get_family_timezone())

    async def test_moves_the_family(self):
        calls = []
        zone = {"timezone": "Europe/Lisbon", "server": "Europe/Paris", "custom": True}
        result = await self.client(Response({"res": zone}), calls).async_set_family_timezone("Europe/Lisbon")
        self.assertEqual(result, zone)
        self.assertEqual(calls, [("PUT", "https://hopla.invalid/eapi/v1/circle/timezone", {"timezone": "Europe/Lisbon"})])

    async def test_a_refusal_keeps_the_server_reason(self):
        with self.assertRaisesRegex(ValueError, "Only parents can do this"):
            await self.client(Response({"error": "Only parents can do this"}, status=403), []).async_set_family_timezone("UTC")


class FamilyTimezoneServiceTests(unittest.TestCase):
    def test_the_service_is_for_parents_and_described(self):
        root = Path(__file__).resolve().parents[1] / "custom_components/hopla"
        source = (root / "__init__.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        service = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                       and node.name == "async_set_family_timezone_service")
        self.assertIn("require_parent", ast.unparse(service))
        services = next(node for node in tree.body if isinstance(node, ast.Assign) and node.targets[0].id == "SERVICES")
        self.assertIn("SERVICE_SET_FAMILY_TIMEZONE", [item.id for item in services.value.elts])
        self.assertIn("set_family_timezone:", (root / "services.yaml").read_text(encoding="utf-8"))
        for name in ("strings.json", "translations/en.json", "translations/fr.json"):
            self.assertIn('"set_family_timezone"', (root / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
