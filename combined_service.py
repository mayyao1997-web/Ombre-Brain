"""Run authenticated Ombre Brain and the optional 187 bridge in one container."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request


def wait_for_ombre(process: subprocess.Popen, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Ombre server exited during startup")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Ombre server did not become healthy in time")


def terminate(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()


def main() -> int:
    ombre = subprocess.Popen([sys.executable, "secure_server.py"])
    bridge: subprocess.Popen | None = None
    discord_bot: subprocess.Popen | None = None

    def stop(*_args) -> None:
        terminate(discord_bot)
        terminate(bridge)
        terminate(ombre)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        wait_for_ombre(ombre)

        if os.environ.get("MCP_ENDPOINT_OMBRE_187", "").strip():
            bridge_env = os.environ.copy()
            bridge_env["OMBRE_MCP_URL"] = "http://127.0.0.1:8000/mcp"
            bridge_env["BRIDGE_METRICS_ENABLED"] = "false"
            bridge = subprocess.Popen(
                [sys.executable, "/app/bridge/start_bridge.py"],
                env=bridge_env,
            )
            print("187 bridge enabled; credentials loaded from environment")
        else:
            print(
                "187 bridge disabled: MCP_ENDPOINT_OMBRE_187 is not configured; "
                "Ombre remains available"
            )

        discord_keys = [
            "DISCORD_BOT_TOKEN",
            "DISCORD_ALLOWED_GUILD_ID",
            "DISCORD_ALLOWED_CHANNEL_ID",
            "MAY_DISCORD_USER_ID",
        ]
        configured = [bool(os.environ.get(key, "").strip()) for key in discord_keys]
        if all(configured):
            discord_bot = subprocess.Popen([sys.executable, "discord_bot.py"])
            print("Discord 187 enabled; credentials and scope loaded from environment")
        elif any(configured):
            print("Discord 187 disabled: configuration is incomplete")
        else:
            print("Discord 187 disabled: no Discord configuration supplied")

        while True:
            if ombre.poll() is not None:
                return ombre.returncode or 1
            if bridge is not None and bridge.poll() is not None:
                return bridge.returncode or 1
            if discord_bot is not None and discord_bot.poll() is not None:
                return discord_bot.returncode or 1
            time.sleep(2)
    finally:
        stop()
        for process in (discord_bot, bridge, ombre):
            if process is not None:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
