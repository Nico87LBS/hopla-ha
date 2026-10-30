"""The family's routes: today's names, or the old ones of a server not yet
updated to Hopla 1.29.0."""
import ast
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest


class HttpError(Exception):
    pass


class Response:
    def __init__(self, body, status=200, content_type="application/json"):
        self.body = body
        self.status = status
        self.content_type = content_type

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.body

    def raise_for_status(self):
        if self.status >= 400:
            raise HttpError(str(self.status))


class FamilyRoutesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "custom_components/hopla/api.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        legacy = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and node.targets[0].id == "LEGACY_FAMILY_PATH")
        client = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        client.body = [node for node in client.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name in ("__init__", "_headers", "async_get_family_members", "_get_members",
                                         "async_get_family_timezone")]
        future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        module = ast.fix_missing_locations(ast.Module(body=[future, legacy, client], type_ignores=[]))
        namespace = {"aiohttp": SimpleNamespace(ClientError=HttpError), "API_TIMEOUT": 10, "Optional": object,
                     "List": list, "json": json, "_LOGGER": logging.getLogger(__name__),
                     "HoplaMember": SimpleNamespace(from_json=lambda data: data["userId"])}
        exec(compile(module, str(source), "exec"), namespace)
        self.client_type = namespace["HoplaApiClient"]

    def client(self, answer, calls):
        def get(url, **kwargs):
            calls.append(url)
            return answer(url)
        return self.client_type("https://hopla.invalid", "token", SimpleNamespace(get=get))

    async def test_uses_the_family_routes(self):
        calls = []
        client = self.client(lambda url: Response([{"userId": 2}]), calls)
        self.assertEqual(await client.async_get_family_members(), [2])
        self.assertEqual(calls, ["https://hopla.invalid/eapi/v1/family/members"])

    async def test_falls_back_on_an_older_server(self):
        calls = []

        def answer(url):
            # An older server answers an unknown route with its web page.
            if "/family/" in url:
                return Response("<html>", content_type="text/html")
            if url.endswith("/timezone"):
                return Response({"res": {"timezone": "Europe/Paris"}})
            return Response([{"userId": 3}, {"userId": 4}])

        client = self.client(answer, calls)
        self.assertEqual(await client.async_get_family_members(), [3, 4])
        self.assertEqual(calls, ["https://hopla.invalid/eapi/v1/family/members",
                                 "https://hopla.invalid/eapi/v1/circle/members"])
        # The other family routes follow.
        calls.clear()
        await client.async_get_family_timezone()
        self.assertEqual(calls, ["https://hopla.invalid/eapi/v1/circle/timezone"])
