import asyncio
import os
import unittest
from unittest.mock import patch

from secure_server import MCPBearerAuth, _required_token


class RecorderApp:
    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


async def invoke(path="/mcp", headers=None):
    downstream = RecorderApp()
    app = MCPBearerAuth(downstream, "x" * 32)
    events = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(event):
        events.append(event)

    encoded_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    await app(
        {"type": "http", "method": "POST", "path": path, "headers": encoded_headers},
        receive,
        send,
    )
    return downstream.called, events


class MCPAuthTests(unittest.TestCase):
    def test_missing_server_token_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                _required_token()

    def test_short_server_token_fails_closed(self):
        with patch.dict(os.environ, {"OMBRE_MCP_TOKEN": "short"}, clear=True):
            with self.assertRaises(RuntimeError):
                _required_token()

    def test_anonymous_mcp_request_is_rejected(self):
        called, events = asyncio.run(invoke())
        self.assertFalse(called)
        self.assertEqual(events[0]["status"], 401)

    def test_wrong_token_is_rejected(self):
        called, events = asyncio.run(
            invoke(headers={"Authorization": "Bearer wrong"})
        )
        self.assertFalse(called)
        self.assertEqual(events[0]["status"], 401)

    def test_correct_bearer_token_reaches_mcp(self):
        called, events = asyncio.run(
            invoke(headers={"Authorization": "Bearer " + "x" * 32})
        )
        self.assertTrue(called)
        self.assertEqual(events[0]["status"], 204)

    def test_health_endpoint_remains_public(self):
        called, events = asyncio.run(invoke(path="/health"))
        self.assertTrue(called)
        self.assertEqual(events[0]["status"], 204)


if __name__ == "__main__":
    unittest.main()
