import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp.server.auth.provider import AuthorizationCode
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl
from starlette.exceptions import HTTPException
from oauth_provider import OmbreOAuthProvider, SCOPE, public_url


class OAuthProviderTests(unittest.TestCase):
    def environment(self, root: str) -> dict[str, str]:
        return {
            "OMBRE_PUBLIC_URL": "https://ombre.example",
            "OMBRE_OAUTH_USERNAME": "May",
            "OMBRE_OAUTH_PASSWORD": "oauth-password-with-entropy",
            "OMBRE_MCP_TOKEN": "m" * 32,
            "OMBRE_BUCKETS_DIR": root,
        }

    def test_public_url_requires_https(self):
        with patch.dict(
            os.environ,
            {
                "OMBRE_PUBLIC_URL": "http://ombre.example",
                "RENDER_EXTERNAL_URL": "",
            },
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                public_url()

    def test_existing_server_bearer_remains_valid(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, self.environment(root), clear=True):
                provider = OmbreOAuthProvider()
                token = asyncio.run(provider.load_access_token("m" * 32))
                self.assertIsNotNone(token)
                self.assertEqual(token.scopes, [SCOPE])
                self.assertIsNone(asyncio.run(provider.load_access_token("wrong")))

    def test_access_and_refresh_tokens_rotate_and_persist(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, self.environment(root), clear=True):
                provider = OmbreOAuthProvider()
                client = OAuthClientInformationFull(
                    client_id="chatgpt-client",
                    redirect_uris=["https://chatgpt.com/callback"],
                    scope=SCOPE,
                )
                asyncio.run(provider.register_client(client))
                issued = provider._issue_tokens(
                    client_id="chatgpt-client",
                    scopes=[SCOPE],
                    resource=provider.resource,
                    subject="May",
                )

                access = asyncio.run(provider.load_access_token(issued.access_token))
                self.assertIsNotNone(access)
                refresh = asyncio.run(
                    provider.load_refresh_token(client, issued.refresh_token)
                )
                self.assertIsNotNone(refresh)

                rotated = asyncio.run(
                    provider.exchange_refresh_token(client, refresh, [SCOPE])
                )
                self.assertNotEqual(rotated.access_token, issued.access_token)
                self.assertIsNone(
                    asyncio.run(provider.load_refresh_token(client, issued.refresh_token))
                )

                restored = OmbreOAuthProvider()
                self.assertIsNotNone(
                    asyncio.run(restored.load_access_token(rotated.access_token))
                )
                if os.name != "nt":
                    state_mode = Path(
                        root, ".oauth-state.json"
                    ).stat().st_mode & 0o777
                    self.assertEqual(state_mode, 0o600)


    def test_handshake_survives_restart_and_bad_login_does_not_consume_state(self):
        class FormRequest:
            async def form(self):
                return {
                    "state": "pending-state",
                    "username": "May",
                    "password": "wrong-password",
                }

        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, self.environment(root), clear=True):
                provider = OmbreOAuthProvider()
                provider.pending["pending-state"] = {
                    "oauth_state": "chatgpt-state",
                    "redirect_uri": "https://chatgpt.com/callback",
                    "redirect_uri_provided_explicitly": True,
                    "code_challenge": "c" * 43,
                    "client_id": "chatgpt-client",
                    "resource": provider.resource,
                    "expires_at": 4102444800,
                    "attempts": 0,
                }
                code = AuthorizationCode(
                    code="authorization-code",
                    scopes=[SCOPE],
                    expires_at=4102444800,
                    client_id="chatgpt-client",
                    code_challenge="c" * 43,
                    redirect_uri=AnyHttpUrl("https://chatgpt.com/callback"),
                    redirect_uri_provided_explicitly=True,
                    resource=provider.resource,
                    subject="May",
                )
                provider.auth_codes["code-hash"] = code
                provider._save_state()

                restored = OmbreOAuthProvider()
                self.assertIn("pending-state", restored.pending)
                self.assertIn("code-hash", restored.auth_codes)

                with self.assertRaises(HTTPException):
                    asyncio.run(restored.login_callback(FormRequest()))
                self.assertIn("pending-state", restored.pending)
                self.assertEqual(restored.pending["pending-state"]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
