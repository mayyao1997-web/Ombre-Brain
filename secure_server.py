"""Secure HTTP entry point for Ombre Brain.

The LLM provider key (OMBRE_API_KEY) is deliberately separate from the
credential protecting the MCP endpoint (OMBRE_MCP_TOKEN).
"""

import os
import secrets

import uvicorn
from starlette.middleware.cors import CORSMiddleware

from server import mcp


MCP_PATH = "/mcp"


def _required_token() -> str:
    token = os.getenv("OMBRE_MCP_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError(
            "OMBRE_MCP_TOKEN must be configured with at least 32 characters "
            "before the remote MCP server can start"
        )
    return token


class MCPBearerAuth:
    """Small ASGI middleware that protects every request under /mcp."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope.get("type") == "http" and (
            path == MCP_PATH or path.startswith(MCP_PATH + "/")
        ):
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            authorization = headers.get("authorization", "")
            candidate = ""
            if authorization.lower().startswith("bearer "):
                candidate = authorization[7:].strip()
            if not candidate:
                candidate = headers.get("ombre-mcp-token", "").strip()

            if not candidate or not secrets.compare_digest(candidate, self.token):
                body = b'{"error":"unauthorized"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("ascii")),
                            (b"www-authenticate", b"Bearer"),
                            (b"cache-control", b"no-store"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return

        await self.app(scope, receive, send)


def create_app():
    token = _required_token()
    app = mcp.streamable_http_app()
    app.add_middleware(MCPBearerAuth, token=token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=[
            "Authorization",
            "Ombre-MCP-Token",
            "Content-Type",
            "Accept",
            "Mcp-Session-Id",
            "Mcp-Protocol-Version",
            "Last-Event-ID",
        ],
        expose_headers=["Mcp-Session-Id"],
    )
    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
