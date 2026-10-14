# Connector setup

What the gateway, and the agents that call it, use. They read this before every job, so keep it
current.

- **Systems:** not set. Each outside system the gateway may reach, the connector (MCP server) name
  for it, what it's used for, and any limits.
- **Direct callers:** the intake triager, the dependency mapper, and the status reporter may call
  the gateway directly. Everyone else goes through Kit.
- **Guard:** `connector-guard.json`, next to this file, sets where the audit log goes and which
  connectors are allowed (`allowed_servers`, by server name; anything not listed is denied). Add a
  tool to `allow_tools` only after checking that it's read-only. For work systems, point
  `audit_dir` at storage your employer manages.
- **Audit log:** one JSON line per request, result, and session end, in monthly files. Result
  contents and credentials are never logged. Say who reviews it.
- **Status:** optional. Connectors that aren't working yet, and why.
