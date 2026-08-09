"""Start the phase-one 187 bridge without persisting secrets in Git."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_TOOLS = ["pulse", "breath"]
DENIED_TOOLS = ["hold", "grow", "trace", "links", "link_buckets"]


def require_environment() -> tuple[str, str, str, int]:
    endpoint = os.environ.get("MCP_ENDPOINT_OMBRE_187", "").strip()
    ombre_url = os.environ.get("OMBRE_MCP_URL", "").strip()
    ombre_token = os.environ.get("OMBRE_MCP_TOKEN", "")
    port_text = os.environ.get("PORT", "10000")

    if not endpoint.startswith("wss://"):
        raise RuntimeError("MCP_ENDPOINT_OMBRE_187 must be a wss:// URL")
    if urlparse(endpoint).query == "":
        raise RuntimeError("MCP_ENDPOINT_OMBRE_187 must include its XiaoZhi token")
    if not ombre_url.startswith("https://") or not ombre_url.endswith("/mcp"):
        raise RuntimeError("OMBRE_MCP_URL must be an https:// URL ending in /mcp")
    if len(ombre_token) < 32:
        raise RuntimeError("OMBRE_MCP_TOKEN must contain at least 32 characters")

    try:
        port = int(port_text)
    except ValueError as exc:
        raise RuntimeError("PORT must be numeric") from exc

    return endpoint, ombre_url, ombre_token, port


def build_config(endpoint: str, ombre_url: str, ombre_token: str) -> dict:
    return {
        "mcpServers": {
            "ombre-187": {
                "type": "streamablehttp",
                "url": ombre_url,
                "headers": {"Authorization": f"Bearer {ombre_token}"},
                "endpoint": endpoint,
                "timeout": 15.0,
                "sse_read_timeout": 300.0,
                "tools": {
                    "allow": ALLOWED_TOOLS,
                    "deny": DENIED_TOOLS,
                },
            }
        }
    }


def write_private_config(config: dict) -> Path:
    fd, path_text = tempfile.mkstemp(prefix="mcp2xiaozhi-", suffix=".json")
    path = Path(path_text)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def main() -> None:
    endpoint, ombre_url, ombre_token, port = require_environment()
    config_path = write_private_config(build_config(endpoint, ombre_url, ombre_token))

    # Never print the endpoint, authorization header, or generated config.
    os.execvp(
        "mcp2xiaozhi",
        [
            "mcp2xiaozhi",
            "--config",
            str(config_path),
            "--log-level",
            "INFO",
            "run",
            "ombre-187",
            "--metrics-port",
            str(port),
            "--metrics-host",
            "0.0.0.0",
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Validation messages contain variable names only, never secret values.
        print(f"bridge startup refused: {exc}", file=sys.stderr)
        raise SystemExit(2)
