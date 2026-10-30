# PPM Express MCP server (ppmx)

A [Model Context Protocol](https://modelcontextprotocol.io) server for PPM Express's public REST API. It
reads portfolios, programs, projects, tasks, key dates, ideas, challenges, and resources, and creates and
updates them, as each caller's personal access token allows. PPM Express's API has no delete, so neither
does this. One package, standard library only, two ways to run it:

| | Kit's connector | Standalone service |
|---|---|---|
| Runs | on your computer (macOS or Windows), started by Claude Code or Claude Desktop | in a container on OpenShift, for a team |
| Transport | MCP over stdio | MCP over Streamable HTTP (stateless, JSON answers) |
| Start | `kit-ppmx serve` | `gunicorn ppmx.server_http:application` (the container's command) |
| Token | yours, from `PPMX_TOKEN`, the Mac Keychain, or Windows Credential Manager | each caller's own, sent with every request |
| Install | `kit-ppmx setup`, and Kit's INSTALL.md (Connectors) | [openshift/INSTALL.md](openshift/INSTALL.md) |

**Status: stub, version 0.2.0.** It runs end to end against `tests/fake_ppmx.py`. Before live use, check
two things against your tenant's endpoint reference (PPM Express > Automation > Swagger):

1. The endpoint paths: `ENDPOINTS` and `PARAMS` in `client.py`, especially the sub-task path
   (`Tasks/bulk`) and the idea stage path (`Ideas/{id}/Stage`), which PPM Express's article doesn't spell
   out.
2. The attribute names the tools read (status, manager, dates, and so on): `FIELDS` in `tools.py`.
   `get_fields` lists a tenant's real ones.

The code tables in `codes.py` are the ones PPM Express publishes: status (0 On Track, 1 At Risk,
2 Critical, 10 Done, -1 N/A), progress (0 Not Started, 1 Completed, 2 In Progress, 3 On Hold,
4 Canceled), the 0-5 rating scale, idea stage (0 Draft to 5 Archived), and key date type (0 Key Date,
1 Milestone, 2 Release). Reads show the labels with the numbers under `codes`; writes take either.

## Tools

Reads (each name starts with a read word): `get_current_user`, `list_portfolios`, `list_programs`,
`list_projects`, `get_project`, `list_tasks`, `list_key_dates`, `list_ideas`, `list_challenges`,
`list_resources`, `get_fields`. Lists filter on the server's side, then come back a page at a time:
`total`, `offset`, `limit`, `sort`, and `next_offset` while there's more.

Changes (each name starts with a write word): `create_project`, `update_project`, `create_task` (a
sub-task with `parent_task_id`), `update_task`, `create_key_date`, `update_key_date`, `create_idea`,
`update_idea`, `set_idea_stage`, and `create_record` and `update_record` for portfolios, programs,
resources, and challenges. They send PPM Express's own formats: a new record's fields under
`attributes`, a change under `updates` (only the fields given), and `{"Stage": n}` for an idea. Fields go
by their keys (`get_fields` lists them, custom fields included); coded fields take a label or a number;
people (`Manager`, `AssignedTo`) take a name, an email, or an ID; `Portfolios` and `Programs` take names
or IDs; `Tags` take text. Each change answers with the record's ID, the field names sent, and the record
as PPM Express now has it.

`python -m ppmx tools` (or `kit-ppmx tools`) lists them all, the changes marked.

## Who can change what

- **The token and PPM Express decide first.** A change needs a token with write scopes (such as Write
  Projects) and the PPM Express permission for it; otherwise PPM Express refuses and the tool says why.
- **`PPMX_WRITES=off`** makes a server read-only: the change tools aren't offered, and a call to one is
  refused before anything is sent.
- **The client asks.** Every change tool is marked as one (not read-only; updates as changing existing
  data), and the server's instructions tell the model to say what it will change and wait for a yes.
  In Kit, Claude Code asks before every change (Kit's permission rules), Kit's agents can't make one (the
  connector guard), and a scheduled run can't either (no one to answer). Claude Desktop asks before a tool
  runs unless you tell it to always allow that tool.
- **Nothing is sent twice.** A change is retried only when PPM Express said it didn't take it (429 or
  503), never after a timeout; then the tool says to check PPM Express before trying again.
- **Every call is recorded.** Both servers write an audit line per tool call: who (a one-way hash of the
  token), the tool, the argument names, the outcome, and for a change, its kind, the record's ID, and the
  field names. Never a token, never a value. Kit's connector also keeps them in Kit's audit folder.

## Settings

Environment variables (Kit's connector also reads them from Kit's config; the container from its
ConfigMap):

| Variable | Default | What it does |
|---|---|---|
| `PPMX_BASE_URL` | none | Your tenant's API address, `https://<host>/@<tenant>/v1.0`, from PPM Express > Automation. https only |
| `PPMX_WRITES` | on | `off` makes the server read-only |
| `PPMX_TIMEOUT` | 20 | Seconds for each request to PPM Express |
| `PPMX_CACHE_SECONDS` | 60 | How long one caller's answers are reused (per caller, never shared; a change clears it); 0 turns it off |
| `PPMX_RATE_PER_MINUTE` | 90 | Requests per caller per minute (Microsoft's PPM Express connector stops at 100) |
| `PPMX_PAGE_SIZE`, `PPMX_MAX_ROWS` | 25, 200 | Rows a list returns by default, and at most |
| `PPMX_CODES_FILE` | none | A JSON file of labels that add to or override the published codes: `{"OverallStatus": {"1": "Watch"}}`; `"KeyDate.Type"` limits a table to one kind of record |
| `PPMX_ALLOWED_ORIGINS` | none | Browser origins the HTTP server accepts; a request from any other is refused |
| `PPMX_MAX_BODY` | 1048576 | The largest request the HTTP server reads, in bytes |
| `PPMX_AUDIT` | on | Audit lines on standard error |
| `PPMX_TOKEN_ENV` | `PPMX_TOKEN` | stdio only: the variable that holds your token |
| `PPMX_TOKEN_KEYCHAIN` | `PPMX_TOKEN` | Kit's connector only: the Keychain or Credential Manager entry, or `off` |

Requests go through `HTTPS_PROXY` when it's set. Redirects aren't followed, so a token can't be sent
anywhere but `PPMX_BASE_URL`.

## Kit's connector (stdio), on macOS or Windows

`kit-ppmx setup` prints the steps for the computer it runs on: store a token (the Keychain on a Mac,
Credential Manager on Windows: `cmdkey /generic:PPMX_TOKEN /user:kit /pass`, which asks for it), set
`PPMX_BASE_URL` in Kit's config, add the server to Claude Code (`claude mcp add --scope user --env
PYTHONUTF8=1 ppmx -- <python> <path>/kit-ppmx serve`) and, if you use it, to Claude Desktop (`kit-ppmx
desktop`, which edits Desktop's config after a backup), and let Kit's agents read through the connector
guard. Then `kit-ppmx check` and `kit-connect test ppmx`. Kit's INSTALL.md has the same steps under
Connectors.

## Standalone (OpenShift)

[openshift/INSTALL.md](openshift/INSTALL.md) has every step: build the image (from macOS, Linux, or
Windows), push it, fill in the settings, deploy with `oc apply -k shared/ppmx/openshift`, check it, and
connect Claude Code. In short: two replicas behind an HTTPS route (TLS at the router), probes on
`/healthz` and `/readyz`, a NetworkPolicy (in from the routers only; out to DNS and HTTPS), no service
account token, all capabilities dropped, a random non-root user, and a read-only root filesystem.
Callers send their own token with every request, in `X-PPMX-Token` (or `Authorization: Bearer` when
nothing in front of the server uses that header).

Clients on your network only: Claude Code connects from the user's computer, but Claude's web and desktop
apps connect to remote connectors from Anthropic's cloud, which can't reach an internal route. On a
laptop, Claude Desktop uses Kit's connector instead.

## Security

- Each caller's own token and PPM Express permissions decide what they can read and change; the server
  adds no access of its own. There's no delete.
- Tokens: passed through, never stored or logged; the audit log names a caller by a one-way hash of the
  token. Answers are cached per caller only. A token with spaces or control characters is refused.
- HTTP: POST `/mcp` with `application/json` only; requests carrying a browser `Origin` not in
  `PPMX_ALLOWED_ORIGINS` are refused; bodies over `PPMX_MAX_BODY` are refused; no event stream or
  sessions.
- What the tools return is data from PPM Express, and the server tells clients to treat it that way.

## Tests

`tests/test_ppmx.py` (the client, the code tables, the read and write tools, both servers, kit-ppmx and
Claude Desktop's config, the connector guard's view of the tool names, and Windows Credential Manager on
Windows) and `tests/ppmx_container_smoke.py` (the image, run as OpenShift runs it), both against
`tests/fake_ppmx.py`. GitHub's checks run them on Linux and Windows, render the OpenShift files, and build
and run the image on every push.
