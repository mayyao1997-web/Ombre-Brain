# StackChan 187 phase-one bridge

This directory is deployed as a separate Render Web Service. It does not run
inside the Ombre-Brain service.

## Render settings

- Root Directory: `bridge`
- Runtime: Docker
- Health Check Path: `/health`
- Auto-Deploy: enabled

Configure these values only in Render Environment:

- `MCP_ENDPOINT_OMBRE_187` — secret; complete XiaoZhi `wss://` endpoint
- `OMBRE_MCP_URL` — `https://ombre-brain-kw68.onrender.com/mcp`
- `OMBRE_MCP_TOKEN` — secret; the same dedicated MCP token configured on Ombre

Do not add a `.env` file to GitHub.

The runtime-generated configuration is stored in a mode-`0600` temporary file.
Production logging is fixed to INFO. Only `pulse` and `breath` are advertised
or callable through the bridge. `hold`, `grow`, `trace`, `links`, and
`link_buckets` are explicitly denied.
