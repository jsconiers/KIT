# Installing the PPM Express MCP server on OpenShift

This guide covers only the standalone service: the PPM Express MCP server running in a container on
OpenShift, for a team. (Kit's own connector, which runs on one person's computer, is in Kit's INSTALL.md
under Connectors.) Commands are shown for macOS or Linux (bash or zsh) and for Windows (PowerShell); where
they're the same, they're shown once.

What you get: two replicas of the server behind an HTTPS route, with TLS ending at the router. Each person
sends their own PPM Express personal access token with every request; the server never stores or logs
it, so each person can read and change only what their own token and PPM Express permissions allow. The
pods run as a random non-root user with a read-only filesystem, no capabilities, no service account
token, and a NetworkPolicy that lets traffic in only from the routers and out only to DNS and HTTPS.

The server reads and writes (it creates and updates; PPM Express's API has no delete). To run a read-only
service, set `PPMX_WRITES` to `"off"` in step 5.

## What you need

| Need | Why | Check |
|---|---|---|
| An OpenShift 4 project (namespace) where you can create a Deployment, Service, Route, ConfigMap, and NetworkPolicy | Where the server runs | `oc auth can-i create deployments -n <namespace>` |
| The `oc` command line | Log in and deploy | `oc version` |
| podman or docker | Build the image (or build it in the cluster: step 2, option B) | `podman --version` |
| A registry the cluster can pull from | Where the image lives | your platform team can say which |
| This repository | The server's code and these files | `git --version` |
| Your tenant's API address | `https://<host>/@<tenant>/v1.0`, from PPM Express > Automation | |
| Outbound HTTPS from the cluster to PPM Express, directly or through a proxy | The server calls PPM Express | your platform team can say which |
| A personal access token | To test the service (yours; it's never stored in the cluster) | PPM Express > Automation |

Before live use, check the endpoint paths and field names against your tenant's endpoint reference (PPM
Express > Automation > Swagger), as `shared/ppmx/README.md` describes. Correcting them means changing
`client.py` or `tools.py` and building a new image.

## 1. Get the code

```bash
git clone https://github.com/<you>/KIT.git
cd KIT
```

Every command below runs from the repository's top folder.

## 2. Build the image

**Option A: on your computer.** The same command works in bash, zsh, and PowerShell:

```bash
podman build --platform linux/amd64 -f shared/ppmx/Containerfile -t ppmx-mcp:0.2.0 .
```

- `--platform linux/amd64` matters on an Apple Silicon Mac: without it the image is built for Arm, and an
  x86 cluster can't run it ("exec format error"). Leave it as is unless your cluster runs on Arm.
- Use docker in place of podman if that's what you have; the options are the same.
- If your organization has an approved base image, add
  `--build-arg BASE_IMAGE=<registry>/<path>/python-312@sha256:<digest>`. It needs Python 3.8 or newer
  and pip.
- If the build can't reach the public Python package index, add your mirror:
  `--build-arg PIP_INDEX_URL=https://<mirror>/simple`. The image installs one package, gunicorn 26.2.0.

**Option B: in the cluster**, if it allows Docker-strategy builds. The image goes to the cluster's own
registry, so there's nothing to push in step 4. Build from a folder holding only the server, with the
Containerfile as its Dockerfile:

```bash
mkdir -p /tmp/ppmx-build/shared && cp -R shared/ppmx /tmp/ppmx-build/shared/
cp shared/ppmx/Containerfile /tmp/ppmx-build/Dockerfile
oc new-build --name ppmx-mcp --strategy docker --binary --to ppmx-mcp:0.2.0
oc start-build ppmx-mcp --from-dir /tmp/ppmx-build --follow
```

```powershell
New-Item -ItemType Directory -Force "$env:TEMP\ppmx-build\shared" | Out-Null
Copy-Item -Recurse -Force shared\ppmx "$env:TEMP\ppmx-build\shared\"
Copy-Item shared\ppmx\Containerfile "$env:TEMP\ppmx-build\Dockerfile"
oc new-build --name ppmx-mcp --strategy docker --binary --to ppmx-mcp:0.2.0
oc start-build ppmx-mcp --from-dir "$env:TEMP\ppmx-build" --follow
```

The image is then `image-registry.openshift-image-registry.svc:5000/<namespace>/ppmx-mcp:0.2.0`. Add
`--build-arg` values to the BuildConfig's `dockerStrategy.buildArgs` if you need them.

## 3. Try it on your computer (optional)

Run the image the way OpenShift will (a random non-root user, read-only), pointing at your tenant:

```bash
podman run --rm -p 8080:8080 --user 1000770000:0 --read-only --tmpfs /tmp \
  -e PPMX_BASE_URL=https://<host>/@<tenant>/v1.0 ppmx-mcp:0.2.0
```

```powershell
podman run --rm -p 8080:8080 --user 1000770000:0 --read-only --tmpfs /tmp `
  -e PPMX_BASE_URL=https://<host>/@<tenant>/v1.0 ppmx-mcp:0.2.0
```

In a second window, check it answers and that your token works. The token is read without showing it, so
it never lands in your shell history:

```bash
curl -s http://localhost:8080/healthz
read -rs PPMX_TOKEN && export PPMX_TOKEN
curl -s http://localhost:8080/mcp -H 'Content-Type: application/json' -H 'Accept: application/json' \
  -H "X-PPMX-Token: $PPMX_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_current_user","arguments":{}}}'
```

```powershell
Invoke-RestMethod http://localhost:8080/healthz
$t = Read-Host "PPM Express token" -AsSecureString
$env:PPMX_TOKEN = [Net.NetworkCredential]::new("", $t).Password
$body = '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_current_user","arguments":{}}}'
Invoke-RestMethod -Method Post -Uri http://localhost:8080/mcp -ContentType "application/json" `
  -Headers @{ "X-PPMX-Token" = $env:PPMX_TOKEN; "Accept" = "application/json" } -Body $body
```

The answer names you and lists the token's scopes. No container handy? From `shared/`, `python -m ppmx
http` runs the same server on Python's own web server (any computer, Windows included; not for
production), with `PPMX_BASE_URL` set in the environment.

## 4. Push the image (option A only)

```bash
podman login <registry>
podman tag ppmx-mcp:0.2.0 <registry>/<namespace>/ppmx-mcp:0.2.0
podman push <registry>/<namespace>/ppmx-mcp:0.2.0
```

If the registry needs credentials to pull, give the project a pull secret, ideally with a robot or
service account's token rather than your own password (`read -rs` keeps it out of your shell history):

```bash
read -rs REGISTRY_TOKEN
oc create secret docker-registry ppmx-pull --docker-server=<registry> --docker-username=<robot account> \
  --docker-password="$REGISTRY_TOKEN"
oc secrets link default ppmx-pull --for=pull
```

## 5. Fill in the settings

All in `shared/ppmx/openshift/`. Nothing here holds a token.

- **`kustomization.yaml`**: `namespace`, and under `images`, `newName` (the image without its tag, for
  example `<registry>/<namespace>/ppmx-mcp`, or the cluster registry's name from option B) and `newTag`
  (`"0.2.0"`).
- **`configmap.yaml`**:
  - `PPMX_BASE_URL`: your tenant's API address.
  - `PPMX_WRITES`: `"on"` offers the create and update tools; `"off"` makes a read-only service.
  - `PPMX_ALLOWED_ORIGINS`: leave empty. Claude Code and other MCP clients don't send a browser origin;
    a browser page that should call the server needs its origin listed here.
  - The rest (rate, cache, page sizes) can stay as they are; `shared/ppmx/README.md` explains each.
  - If the cluster reaches the internet through a proxy, add `HTTPS_PROXY: "http://<proxy>:<port>"` and
    `NO_PROXY: ".cluster.local,.svc"`.
- **`route.yaml`**: leave `spec.host` out to get a generated name, or set it. If your cluster has an
  internal router for internal-only routes, ask the platform team which label puts a route on it, and add
  that label under `metadata.labels`.
- **`networkpolicy.yaml`**: it lets traffic in only from the OpenShift routers, and out only to DNS and
  port 443. With a proxy, add its port to the egress rule. A NetworkPolicy can't name a host; if the
  platform team wants egress limited to your PPM Express host, that's an EgressFirewall (OVN-Kubernetes)
  they manage.

See what will be applied before you apply it:

```bash
oc kustomize shared/ppmx/openshift
```

## 6. Deploy

```bash
oc login --server=https://api.<cluster>:6443     # or "Copy login command" in the web console
oc project <namespace>
oc apply -k shared/ppmx/openshift
oc rollout status deploy/ppmx-mcp
oc get route ppmx-mcp -o jsonpath='{.spec.host}'
```

The last line prints the route's host name, used below as `<route-host>`.

## 7. Check it

```bash
curl -s https://<route-host>/healthz        # {"status": "ok"}
curl -s https://<route-host>/readyz         # {"status": "ready"}, or 503 with the reason
curl -s https://<route-host>/mcp -H 'Content-Type: application/json' -H 'Accept: application/json' \
  -H "X-PPMX-Token: $PPMX_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_current_user","arguments":{}}}'
```

In PowerShell, use the `Invoke-RestMethod` lines from step 3 with `https://<route-host>`. Then look at
the audit lines (one JSON line per call, with a hash of the token, never the token):

```bash
oc logs deploy/ppmx-mcp --tail=20
```

## 8. Connect Claude Code

Each person sets their own token in their environment: step 3 shows how to read it without echoing it.
On a Mac, `export PPMX_TOKEN="$(security find-generic-password -s PPMX_TOKEN -w)"` in `~/.zshrc` takes it
from the Keychain. On Windows, after the step 3 lines, `[Environment]::SetEnvironmentVariable("PPMX_TOKEN",
$env:PPMX_TOKEN, "User")` keeps it for your account (open a new window afterward). Then add the server to
a project. The single quotes keep `${PPMX_TOKEN}` as written, so
Claude Code fills it in when it connects and the token never lands in a file:

```bash
claude mcp add --scope project --transport http ppmx https://<route-host>/mcp --header 'X-PPMX-Token: ${PPMX_TOKEN}'
```

That writes `.mcp.json` in the project folder:

```json
{"mcpServers": {"ppmx": {"type": "http", "url": "https://<route-host>/mcp",
                         "headers": {"X-PPMX-Token": "${PPMX_TOKEN}"}}}}
```

Claude Code asks you to approve a project's servers the first time. It asks before each tool call until
you allow a tool; keep the `create_` and `update_` tools on asking.

**Claude Desktop and claude.ai** connect to remote servers from Anthropic's cloud, which can't reach a
route inside your network, so they can't use this service. On a laptop, Claude Desktop uses Kit's own
connector instead (`kit-ppmx desktop`; Kit's INSTALL.md, Connectors).

## 9. Run it

| Task | How |
|---|---|
| Update to a new version | Build and push the new tag (steps 2 and 4), set `newTag`, `oc apply -k shared/ppmx/openshift`, `oc rollout status deploy/ppmx-mcp` |
| Undo an update | `oc rollout undo deploy/ppmx-mcp` |
| Make it read-only, or change any setting | Edit `configmap.yaml`, `oc apply -k shared/ppmx/openshift`, then `oc rollout restart deploy/ppmx-mcp` (pods read settings when they start) |
| See the audit lines | `oc logs -l app.kubernetes.io/name=ppmx-mcp --tail=200`; the cluster's log collector keeps them longer |
| Run more copies | `oc scale deploy/ppmx-mcp --replicas=3` (each pod keeps its own short cache; nothing else is shared) |
| Remove it | `oc delete -k shared/ppmx/openshift` |

## Troubleshooting

| What you see | What to do |
|---|---|
| `/readyz` is 503 | Its `reason` says what's wrong with `PPMX_BASE_URL` (missing, not https, has a user name). Fix the ConfigMap, apply, restart |
| A tool says PPM Express rejected the token | It expired or was revoked: create a new one in PPM Express > Automation |
| A tool says PPM Express refused (403) | The token lacks the scope (a change needs a write scope such as Write Projects) or your PPM Express permissions don't allow it |
| "couldn't reach PPM Express" | Egress is blocked: the NetworkPolicy, an EgressFirewall, or a proxy the pods don't know about (`HTTPS_PROXY`) |
| "couldn't confirm PPM Express made the change" | The change timed out after it was sent. Look in PPM Express before trying again; the server never resends a change |
| `ImagePullBackOff` | The image name in `kustomization.yaml`, or a missing pull secret (step 4) |
| `exec format error` | The image was built for Arm: rebuild with `--platform linux/amd64` |
| `CrashLoopBackOff` with permission errors | The image wasn't built from this Containerfile (the code must be group-readable for OpenShift's random user) |
| The route answers 503 | No pod is ready yet: `oc get pods`, `oc describe pod <pod>`, and `/readyz` |
| A call from a web page gets 403 | Its origin isn't in `PPMX_ALLOWED_ORIGINS` |

## Security notes

- The service adds no access of its own: each request carries one person's token, and PPM Express
  checks that token's scopes and that person's permissions. There's no delete.
- Tokens are passed through and never stored, cached, or logged; answers are cached per person for a
  minute and a person's change clears their cache. The audit lines name a person only by a one-way hash
  of their token, and record argument and field names, never values.
- Keep the route on an internal router. To require single sign-on as well, put it in front of the route;
  people then send their PPM Express token in `X-PPMX-Token`, leaving `Authorization` to the sign-on.
