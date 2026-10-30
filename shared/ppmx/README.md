# PPM Express MCP server (ppmx)

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server for PPM Express's public REST
API: portfolios, programs, projects, tasks, key dates, ideas, and resources, as each caller's personal
access token can see them. One package, standard library only, two ways to run it:

| | Kit's connector | Standalone service |
|---|---|---|
| Runs | on your computer, started by Claude Code | in a container on OpenShift, for a team |
| Transport | MCP over stdio | MCP over Streamable HTTP (stateless, JSON answers) |
| Start | `kit-ppmx serve` | `gunicorn ppmx.server_http:application` (the container's command) |
| Token | yours, from `PPMX_TOKEN` or the Mac Keychain | each caller's own, sent with every request |

**Status: stub, version 0.1.0.** It runs end to end against `tests/fake_ppmx.py`. Before live use, check
three things against your tenant's endpoint reference (PPM Express > Automation > Swagger):

1. The endpoint paths: `ENDPOINTS` and `PARAMS` in `client.py`.
2. The attribute names the tools read (status, manager, dates, and so on): `FIELDS` in `tools.py`.
   `get_fields` lists a tenant's real ones.
3. The code tables: PPM Express returns numbers for statuses, progress, key date type, idea stage, and
   ratings. Until `TABLES` in `codes.py` (or a `PPMX_CODES_FILE`) has them, those stay numbers, and
   "open" and "overdue" can't tell a finished task by its status (the answer says so in `notes`).

## Tools

All read-only, each name starting with a read word, as Kit's connector guard requires:
`get_current_user`, `list_portfolios`, `list_programs`, `list_projects`, `get_project`, `list_tasks`,
`list_key_dates`, `list_ideas`, `list_resources`, `get_fields`. Lists filter on the server's side, then
come back a page at a time: `total`, `offset`, `limit`, `sort`, and `next_offset` while there's more.
`python -m ppmx tools` (or `kit-ppmx tools`) lists them with their descriptions.

## Settings

Environment variables (Kit's connector also reads them from Kit's config; the container from its
ConfigMap):

| Variable | Default | What it does |
|---|---|---|
| `PPMX_BASE_URL` | none | Your tenant's API address, `https://<host>/@<tenant>/v1.0`, from PPM Express > Automation. https only |
| `PPMX_TIMEOUT` | 20 | Seconds for each request to PPM Express |
| `PPMX_CACHE_SECONDS` | 60 | How long one caller's answers are reused (per caller, never shared); 0 turns it off |
| `PPMX_RATE_PER_MINUTE` | 90 | Requests per caller per minute (Microsoft's PPM Express connector stops at 100) |
| `PPMX_PAGE_SIZE`, `PPMX_MAX_ROWS` | 25, 200 | Rows a list returns by default, and at most |
| `PPMX_CODES_FILE` | none | A JSON file of code tables: `{"OverallStatus": {"1": "On track"}}` |
| `PPMX_ALLOWED_ORIGINS` | none | Browser origins the HTTP server accepts; a request from any other is refused |
| `PPMX_MAX_BODY` | 1048576 | The largest request the HTTP server reads, in bytes |
| `PPMX_AUDIT` | on | The HTTP server's audit lines on standard error |
| `PPMX_TOKEN_ENV` | `PPMX_TOKEN` | stdio only: the variable that holds your token |

Requests go through `HTTPS_PROXY` when it's set. Redirects aren't followed, so a token can't be sent
anywhere but `PPMX_BASE_URL`.

## Kit's connector (stdio)

`kit-ppmx setup` prints the steps for the computer it runs on: store a token with read scopes (the
Keychain on a Mac, a user environment variable on Windows), set `PPMX_BASE_URL` in Kit's config, add the
server to Claude Code (`claude mcp add --scope user --env PYTHONUTF8=1 ppmx -- python3 <path>/kit-ppmx
serve`), and allow it in Kit's connector guard. Then `kit-ppmx check` and `kit-connect test ppmx`.
Agents reach it through the gateway, so every call is checked and logged by the connector guard.

## Standalone (OpenShift)

Build from the repository root, and try it the way OpenShift runs it (a random non-root user, read-only):

    podman build -f shared/ppmx/Containerfile -t ppmx-mcp:0.1.0 .
    podman run --rm -p 8080:8080 --user 1000770000:0 --read-only --tmpfs /tmp \
      -e PPMX_BASE_URL=https://<host>/@<tenant>/v1.0 ppmx-mcp:0.1.0

Deploy: push the image to your registry, fill in the `REPLACE` values in `openshift/`, and `oc apply -k
shared/ppmx/openshift`. That makes two replicas behind an HTTPS route (TLS at the router), probes on
`/healthz` and `/readyz`, a NetworkPolicy (in from the routers only; out to DNS and HTTPS), no service
account token, all capabilities dropped, and a read-only root filesystem.

Callers send their own token with every request, in `X-PPMX-Token` (or `Authorization: Bearer` when
nothing in front of the server uses that header). In Claude Code, a project's `.mcp.json` can read it
from the caller's environment, so it never sits in the file:

    {"mcpServers": {"ppmx": {"type": "http", "url": "https://<route-host>/mcp",
                             "headers": {"X-PPMX-Token": "${PPMX_TOKEN}"}}}}

Clients on your network only: Claude Code connects from the user's computer, but Claude's web and desktop
apps connect to custom connectors from Anthropic's cloud, which can't reach an internal route.

## Security

- Read-only: no tool writes, and PPM Express's own permissions and the token's scopes still apply.
- Tokens: passed through, never stored or logged; the audit log names a caller by a one-way hash of the
  token. Answers are cached per caller only. A token with spaces or control characters is refused.
- HTTP: POST `/mcp` with `application/json` only; requests carrying a browser `Origin` not in
  `PPMX_ALLOWED_ORIGINS` are refused; bodies over `PPMX_MAX_BODY` are refused; no event stream or
  sessions. The audit log has the method, tool, argument names (not values), outcome, rows, and time.
- What the tools return is data from PPM Express, and the server tells clients to treat it that way.

## Tests

`tests/test_ppmx.py` (the client, tools, both servers, and the connector guard's view of the tool names)
and `tests/ppmx_container_smoke.py` (the image, run as OpenShift runs it), both against
`tests/fake_ppmx.py`. GitHub's checks run them, and render the OpenShift files, on every push.
