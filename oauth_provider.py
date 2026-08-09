"""Single-user OAuth 2.1 provider for ChatGPT MCP access.

The existing long-lived OMBRE_MCP_TOKEN remains valid for trusted server-to-server
clients. Browser OAuth uses a separate password and short-lived access tokens.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import secrets
import stat
import time
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


SCOPE = "ombre"
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 24 * 3600


class OmbreRefreshToken(RefreshToken):
    resource: str | None = None


def oauth_enabled() -> bool:
    return bool(os.environ.get("OMBRE_OAUTH_PASSWORD", "").strip())


def public_url() -> str:
    value = (
        os.environ.get("OMBRE_PUBLIC_URL", "").strip()
        or os.environ.get("RENDER_EXTERNAL_URL", "").strip()
    ).rstrip("/")
    if not value.startswith("https://"):
        raise RuntimeError("OMBRE_PUBLIC_URL must be an HTTPS origin when OAuth is enabled")
    return value


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OmbreOAuthProvider(
    OAuthAuthorizationServerProvider[
        AuthorizationCode, OmbreRefreshToken, AccessToken
    ]
):
    def __init__(self) -> None:
        self.origin = public_url()
        self.resource = self.origin + "/mcp"
        self.username = os.environ.get("OMBRE_OAUTH_USERNAME", "May").strip() or "May"
        self.password = os.environ.get("OMBRE_OAUTH_PASSWORD", "")
        if len(self.password) < 16:
            raise RuntimeError("OMBRE_OAUTH_PASSWORD must contain at least 16 characters")
        self.fixed_token = os.environ.get("OMBRE_MCP_TOKEN", "")
        if len(self.fixed_token) < 32:
            raise RuntimeError("OMBRE_MCP_TOKEN must contain at least 32 characters")

        buckets_dir = Path(os.environ.get("OMBRE_BUCKETS_DIR", "buckets"))
        self.state_path = Path(
            os.environ.get(
                "OMBRE_OAUTH_STATE_FILE",
                str(buckets_dir / ".oauth-state.json"),
            )
        )
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.access_tokens: dict[str, dict[str, Any]] = {}
        self.refresh_tokens: dict[str, dict[str, Any]] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.pending: dict[str, dict[str, Any]] = {}
        self._load_state()

    def _load_state(self) -> None:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception as exc:
            raise RuntimeError("OAuth state file is unreadable") from exc

        self.clients = {
            key: OAuthClientInformationFull.model_validate(value)
            for key, value in raw.get("clients", {}).items()
        }
        now = int(time.time())
        self.access_tokens = {
            key: value
            for key, value in raw.get("access_tokens", {}).items()
            if int(value.get("expires_at", 0)) > now
        }
        self.refresh_tokens = {
            key: value
            for key, value in raw.get("refresh_tokens", {}).items()
            if int(value.get("expires_at", 0)) > now
        }
        self.auth_codes = {
            key: AuthorizationCode.model_validate(value)
            for key, value in raw.get("auth_codes", {}).items()
            if float(value.get("expires_at", 0)) > now
        }
        self.pending = {
            key: value
            for key, value in raw.get("pending", {}).items()
            if float(value.get("expires_at", 0)) > now
        }

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "clients": {
                key: value.model_dump(mode="json", exclude_none=True)
                for key, value in self.clients.items()
            },
            "access_tokens": self.access_tokens,
            "refresh_tokens": self.refresh_tokens,
            "auth_codes": {
                key: value.model_dump(mode="json", exclude_none=True)
                for key, value in self.auth_codes.items()
            },
            "pending": self.pending,
        }
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        temporary.replace(self.state_path)
        os.chmod(self.state_path, stat.S_IRUSR | stat.S_IWUSR)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("client_id is required")
        self.clients[client_info.client_id] = client_info
        self._save_state()

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        state_key = secrets.token_urlsafe(32)
        self.pending[state_key] = {
            "oauth_state": params.state,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "code_challenge": params.code_challenge,
            "client_id": client.client_id,
            "resource": params.resource or self.resource,
            "expires_at": time.time() + 1800,
            "attempts": 0,
        }
        self._save_state()
        return f"{self.origin}/oauth/login?state={state_key}"

    async def login_page(self, request: Request) -> HTMLResponse:
        state = request.query_params.get("state", "")
        pending = self.pending.get(state)
        if not pending or pending["expires_at"] < time.time():
            if pending:
                self.pending.pop(state, None)
                self._save_state()
            raise HTTPException(400, "Invalid or expired authorization request")
        safe_state = html.escape(state, quote=True)
        return HTMLResponse(
            f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Ombre Brain 授权</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font-family:system-ui;max-width:420px;margin:60px auto;padding:24px}}
input,button{{box-sizing:border-box;width:100%;padding:12px;margin-top:10px}}
button{{cursor:pointer}}</style></head>
<body><h2>连接 Ombre Brain</h2>
<p>登录后，ChatGPT 将能够调用你批准的长期记忆工具。</p>
<form method="post" action="/oauth/login/callback">
<input type="hidden" name="state" value="{safe_state}">
<label>用户名<input name="username" autocomplete="username" required></label>
<label>密码<input type="password" name="password" autocomplete="current-password" required></label>
<button type="submit">授权连接</button></form></body></html>""",
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; "
                    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def login_callback(self, request: Request) -> Response:
        form = await request.form()
        state = form.get("state")
        username = form.get("username")
        password = form.get("password")
        if not all(isinstance(value, str) for value in (state, username, password)):
            raise HTTPException(400, "Invalid login request")

        pending = self.pending.get(state)
        if not pending or pending["expires_at"] < time.time():
            raise HTTPException(400, "Invalid or expired authorization request")
        valid_user = secrets.compare_digest(username, self.username)
        valid_password = secrets.compare_digest(password, self.password)
        if not (valid_user and valid_password):
            pending["attempts"] = int(pending.get("attempts", 0)) + 1
            if pending["attempts"] >= 5:
                self.pending.pop(state, None)
            self._save_state()
            raise HTTPException(401, "Invalid credentials")

        # Keep the request alive until its short expiry. Render can be slow enough
        # that a user submits twice; each valid submission receives its own
        # distinct, single-use authorization code.
        pending["attempts"] = 0

        code_value = secrets.token_urlsafe(32)
        code = AuthorizationCode(
            code=code_value,
            client_id=pending["client_id"],
            redirect_uri=AnyHttpUrl(pending["redirect_uri"]),
            redirect_uri_provided_explicitly=pending[
                "redirect_uri_provided_explicitly"
            ],
            expires_at=time.time() + 300,
            scopes=[SCOPE],
            code_challenge=pending["code_challenge"],
            resource=pending["resource"],
            subject=self.username,
        )
        self.auth_codes[_digest(code_value)] = code
        self._save_state()
        callback_uri = construct_redirect_uri(
            pending["redirect_uri"],
            code=code_value,
            state=pending["oauth_state"],
            iss=self.origin,
        )
        safe_callback_uri = html.escape(callback_uri, quote=True)
        return HTMLResponse(
            f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>授权成功</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="1;url={safe_callback_uri}">
<style>body{{font-family:system-ui;max-width:420px;margin:60px auto;padding:24px}}
a{{display:block;padding:12px;text-align:center;background:#111;color:#fff;
text-decoration:none;border-radius:8px}}</style></head>
<body><h2>授权成功</h2><p>正在返回 ChatGPT。如果没有自动跳转，请点击下面的按钮。</p>
<a href="{safe_callback_uri}">继续返回 ChatGPT</a></body></html>""",
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; "
                    "base-uri 'none'; frame-ancestors 'none'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self.auth_codes.get(_digest(authorization_code))
        if not code or code.expires_at < time.time():
            return None
        if code.client_id != client.client_id:
            return None
        return code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        code_hash = _digest(authorization_code.code)
        if self.auth_codes.pop(code_hash, None) is None:
            raise TokenError("invalid_grant", "Authorization code is invalid or used")
        self._save_state()
        return self._issue_tokens(
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            resource=authorization_code.resource or self.resource,
            subject=authorization_code.subject or self.username,
        )

    def _issue_tokens(
        self, client_id: str, scopes: list[str], resource: str, subject: str
    ) -> OAuthToken:
        now = int(time.time())
        access = secrets.token_urlsafe(48)
        refresh = secrets.token_urlsafe(48)
        self.access_tokens[_digest(access)] = {
            "client_id": client_id,
            "scopes": scopes,
            "expires_at": now + ACCESS_TTL,
            "resource": resource,
            "subject": subject,
        }
        self.refresh_tokens[_digest(refresh)] = {
            "client_id": client_id,
            "scopes": scopes,
            "expires_at": now + REFRESH_TTL,
            "resource": resource,
            "subject": subject,
        }
        self._save_state()
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TTL,
            refresh_token=refresh,
            scope=" ".join(scopes),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        if secrets.compare_digest(token, self.fixed_token):
            return AccessToken(
                token=token,
                client_id="trusted-server-client",
                scopes=[SCOPE],
                resource=self.resource,
                subject="server",
            )
        data = self.access_tokens.get(_digest(token))
        if not data or data["expires_at"] < time.time():
            return None
        return AccessToken(token=token, **data)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> OmbreRefreshToken | None:
        data = self.refresh_tokens.get(_digest(refresh_token))
        if not data or data["expires_at"] < time.time():
            return None
        if data["client_id"] != client.client_id:
            return None
        return OmbreRefreshToken(token=refresh_token, **data)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: OmbreRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        old_hash = _digest(refresh_token.token)
        if self.refresh_tokens.pop(old_hash, None) is None:
            raise TokenError("invalid_grant", "Refresh token is invalid or used")
        requested = scopes or refresh_token.scopes
        if not set(requested).issubset(refresh_token.scopes):
            raise TokenError("invalid_scope", "Requested scope exceeds original grant")
        return self._issue_tokens(
            client_id=client.client_id or "",
            scopes=requested,
            resource=refresh_token.resource or self.resource,
            subject=refresh_token.subject or self.username,
        )

    async def revoke_token(
        self, token: AccessToken | OmbreRefreshToken
    ) -> None:
        token_hash = _digest(token.token)
        self.access_tokens.pop(token_hash, None)
        self.refresh_tokens.pop(token_hash, None)
        self._save_state()
