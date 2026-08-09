import os
import tempfile
import unittest
from unittest.mock import patch

from start_bridge import ALLOWED_TOOLS, build_config, require_environment, write_private_config


class BridgeConfigTests(unittest.TestCase):
    def test_only_read_tools_are_allowed(self):
        config = build_config(
            "wss://api.xiaozhi.me/mcp/?token=secret",
            "https://example.com/mcp",
            "x" * 32,
        )
        tools = config["mcpServers"]["ombre-187"]["tools"]
        self.assertEqual(tools["allow"], ["pulse", "breath"])
        self.assertNotIn("hold", tools["allow"])
        self.assertIn("hold", tools["deny"])
        self.assertIn("grow", tools["deny"])
        self.assertIn("trace", tools["deny"])

    def test_missing_secrets_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                require_environment()

    def test_runtime_config_is_owner_only(self):
        path = write_private_config({"test": True})
        try:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
