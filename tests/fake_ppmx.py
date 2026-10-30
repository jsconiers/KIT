#!/usr/bin/env python3
"""fake_ppmx: a stand-in for PPM Express's public API, for the PPM Express MCP server's tests and the
container smoke test. Two people with their own tokens see different projects, so a test can tell one
caller's data from another's. The paths follow shared/ppmx/client.py's ENDPOINTS (provisional, as they
are), coded fields come back as numbers with PPM Express's published codes, and writes work the way PPM
Express's API article describes: POST {"attributes": {...}} to create, PATCH {"updates": {...}} to
change, POST {"Stage": n} to move an idea, and a list of {"ParentID", "attributes"} for sub-tasks. Each
fake has its own copy of the data, so one test's writes never leak into another's.

  python3 tests/fake_ppmx.py [--port 18080]     serve http://127.0.0.1:PORT/@test/v1.0 until stopped

Tokens: token-alex-0001 (Alex: read and write scopes), token-blake-0002 (Blake: read only, so a change
gets 403), token-busy-0003 (answers 429 once per path, then like Alex). Anything else gets 401. Alex's
project list comes back in two pages (nextLink).
"""
import argparse
import copy
import json
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREFIX = "/@test/v1.0"
TOKENS = {"token-alex-0001": "alex", "token-blake-0002": "blake", "token-busy-0003": "busy"}
ME = {"alex": {"logonAccount": "alex", "email": "alex@example.com", "displayName": "Alex Rivera"},
      "blake": {"logonAccount": "blake", "email": "blake@example.com", "displayName": "Blake Chen"}}
SCOPES = {"alex": ["Read Projects", "Write Projects", "Read Resources", "Write Resources"],
          "blake": ["Read Projects"]}

P1, P2 = "aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002"
G1 = "bbbbbbbb-0000-4000-8000-000000000001"
A1, A2, A3 = ("cccccccc-0000-4000-8000-000000000001", "cccccccc-0000-4000-8000-000000000002",
              "cccccccc-0000-4000-8000-000000000003")
B1 = "dddddddd-0000-4000-8000-000000000001"
C1 = "eeeeeeee-0000-4000-8000-000000000001"
T1, T2, T3, T4 = ("f0000000-0000-4000-8000-000000000001", "f0000000-0000-4000-8000-000000000002",
                  "f0000000-0000-4000-8000-000000000003", "f0000000-0000-4000-8000-000000000004")
K1, K2, K3 = ("90000000-0000-4000-8000-000000000001", "90000000-0000-4000-8000-000000000002",
              "90000000-0000-4000-8000-000000000003")
I1, I2 = "70000000-0000-4000-8000-000000000001", "70000000-0000-4000-8000-000000000002"
R1, R2 = "60000000-0000-4000-8000-000000000001", "60000000-0000-4000-8000-000000000002"


def item(id_, **attributes):
    return {"id": id_, "attributes": attributes}


# Codes as PPM Express publishes them. Status: 0 On Track, 1 At Risk, 2 Critical, 10 Done. Progress:
# 0 Not Started, 1 Completed, 2 In Progress. Key date type: 0 Key Date, 1 Milestone. Idea stage: 1
# Proposed, 2 Active.
DATA = {
    "portfolios": {"alex": [item(P1, Name="Digital", Manager="Alex Rivera", OverallStatus=0),
                            item(P2, Name="Infrastructure", Manager="Sam Lee", OverallStatus=1)],
                   "blake": [item(P1, Name="Digital", Manager="Alex Rivera", OverallStatus=0)]},
    "programs": {"alex": [item(G1, Name="Cloud migration", Manager="Sam Lee", Portfolios=["Infrastructure"])],
                 "blake": []},
    "projects": {
        "alex": [item(A1, Name="Network refresh", OverallStatus=0, Manager="Alex Rivera", StartDate="2026-09-01T00:00:00",
                      FinishDate="2027-03-31T00:00:00", Portfolios=["Infrastructure"], Programs=["Cloud migration"],
                      Progress=2, Description="Replace the core switches."),
                 item(A2, Name="Data center exit", OverallStatus=2, Manager="Sam Lee", StartDate="2026-01-15T00:00:00",
                      FinishDate="2026-12-15T00:00:00", Portfolios=["Infrastructure"], Programs=["Cloud migration"],
                      Progress=2),
                 item(A3, Name="Mobile app", OverallStatus=0, Manager="Alex Rivera", StartDate="2026-11-01T00:00:00",
                      Portfolios=["Digital"], Progress=0)],
        "blake": [item(B1, Name="Payments upgrade", OverallStatus=1, Manager="Blake Chen",
                       StartDate="2026-08-01T00:00:00", FinishDate="2026-11-20T00:00:00", Portfolios=["Digital"])],
    },
    "tasks": {A1: [item(T1, Name="Order switches", Status=0, Progress=2,
                        AssignedTo={"name": "Sam Lee", "email": "sam@example.com"}, DueDate="2026-10-20T00:00:00"),
                   item(T2, Name="Design review", Status=10, Progress=1,
                        AssignedTo={"name": "Alex Rivera"}, DueDate="2026-10-01T00:00:00"),
                   item(T3, Name="Cutover plan", Status=0, Progress=0,
                        AssignedTo={"name": "Alex Rivera"}, DueDate="2026-11-12T00:00:00"),
                   {**item(T4, Name="Jira epic: firmware", Status=1, Progress=2, DueDate="2026-12-01T00:00:00"),
                    "sourceType": "Jira"}]},
    "key_dates": {A1: [item(K1, Name="Design approved", Date="2026-10-01T00:00:00", Type=0, Status=10),
                       item(K2, Name="Go-live", Date="2026-11-30T00:00:00", Type=1, Status=0),
                       item(K3, Name="Vendor contract", Date="2026-10-15T00:00:00", Type=1, Status=1)]},
    "ideas": [{**item(I1, Name="Self-service portal", Stage=1), "votes": 4},
              {**item(I2, Name="AI triage", Stage=2), "votes": 9, "challengeId": C1}],
    "challenges": [item(C1, Name="Service desk of the future", Status=0)],
    "resources": [item(R1, Name="Alex Rivera", Email="alex@example.com"),
                  item(R2, Name="Sam Lee", Email="sam@example.com")],
}
FIELDS = {"Project": [{"key": "Name", "label": "Name", "type": "Text", "isMultiChoice": False, "isReadonly": False},
                      {"key": "OverallStatus", "label": "Overall Status", "type": "Choice", "isMultiChoice": False,
                       "isReadonly": False, "settings": {"options": [0, 1, 2, 10]}}]}
SHARED = {"Portfolios": "portfolios", "Programs": "programs", "Resources": "resources", "Challenges": "challenges",
          "Ideas": "ideas"}


class Fake:
    """One fake's state: its own copy of the data, request counts per (user, path), the writes it took
    (who, method, path, body), and which busy paths have answered 429."""

    def __init__(self):
        self.data = copy.deepcopy(DATA)
        self.hits = {}
        self.writes = []
        self.busy_done = set()
        self.lock = threading.Lock()

    def count(self, who, path):
        with self.lock:
            self.hits[(who, path)] = self.hits.get((who, path), 0) + 1

    def table(self, kind, who):
        """The list a kind of record lives in for this caller: per person for portfolios, programs, and
        projects (as visibility differs), shared for the rest."""
        value = self.data[kind]
        return value.setdefault(who, []) if isinstance(value, dict) else value


def make_handler(fake):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body=None, headers=()):
            data = b"" if body is None else json.dumps(body).encode("utf-8")
            self.send_response(status)
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def who(self):
            """(user, path, query) for an allowed request, or None when an answer has been sent."""
            auth = self.headers.get("Authorization") or ""
            who = TOKENS.get(auth[7:]) if auth.startswith("Bearer ") else None
            if not who:
                self.send(401, {"error": "unauthorized"})
                return None
            url = urllib.parse.urlsplit(self.path)
            if not url.path.startswith(PREFIX + "/"):
                self.send(404, {"error": "not found"})
                return None
            path = url.path[len(PREFIX) + 1:]
            fake.count(who, url.path + ("?" + url.query if url.query else ""))
            if who == "busy":
                with fake.lock:
                    first = (self.command, path) not in fake.busy_done
                    fake.busy_done.add((self.command, path))
                if first:
                    self.send(429, {"error": "slow down"}, [("Retry-After", "0")])
                    return None
                who = "alex"
            return who, path, urllib.parse.parse_qs(url.query)

        # ---- reads
        def do_GET(self):  # noqa: N802
            got = self.who()
            if not got:
                return
            who, path, query = got
            parts = path.split("/")
            base = f"http://{self.headers.get('Host')}{PREFIX}"
            if path == "Me":
                return self.send(200, {"data": {"id": "50000000-0000-4000-8000-00000000000" + ("1" if who == "alex" else "2"),
                                                **ME[who], "token": {"id": "t-1", "name": "kit",
                                                "expirationDate": "2027-01-31T00:00:00Z", "scopes": SCOPES[who]}}})
            if path == "Projects":
                rows = fake.table("projects", who)
                if who == "alex" and len(rows) > 2:   # pages of two, joined by next links
                    page = int((query.get("page") or ["1"])[0])
                    out = {"data": rows[(page - 1) * 2:page * 2]}
                    if page * 2 < len(rows):
                        out["nextLink"] = f"{base}/Projects?page={page + 1}"
                    return self.send(200, out)
                return self.send(200, {"data": rows})
            if path in SHARED:
                rows = fake.table(SHARED[path], who)
                if path == "Ideas" and query.get("challengeId"):
                    rows = [i for i in rows if i.get("challengeId") == query["challengeId"][0]]
                return self.send(200, {"data": rows})
            if len(parts) >= 2 and parts[0] == "Projects":
                project = self.project(who, parts[1])
                if project is None:
                    return None
                if len(parts) == 2:
                    return self.send(200, {"data": project})
                if parts[2] == "Tasks":
                    return self.send(200, {"data": fake.data["tasks"].get(parts[1], [])})
                if parts[2] == "KeyDates":
                    return self.send(200, {"data": fake.data["key_dates"].get(parts[1], [])})
            if len(parts) == 2 and parts[0] == "Fields":
                return self.send(200, {"data": FIELDS.get(parts[1], [])})
            if path == "Redirect":                    # a client must not follow this with the token
                return self.send(302, None, [("Location", "http://127.0.0.1:9/steal")])
            return self.send(404, {"error": "not found"})

        def project(self, who, pid):
            found = [p for p in fake.table("projects", who) if p["id"] == pid]
            if not found:
                self.send(404, {"error": "no such project"})
                return None
            return found[0]

        # ---- writes
        def do_POST(self):  # noqa: N802
            self.write("POST")

        def do_PATCH(self):  # noqa: N802
            self.write("PATCH")

        def write(self, method):
            got = self.who()
            if not got:
                return
            who, path, query = got
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"null")
            except ValueError:
                return self.send(400, {"error": "the body isn't JSON"})
            if (self.headers.get("Content-Type") or "").split(";")[0] != "application/json":
                return self.send(415, {"error": "send JSON"})
            if not any(s.startswith("Write") for s in SCOPES[who]):
                return self.send(403, {"error": "the token has no write scope"})
            with fake.lock:
                fake.writes.append((who, method, path, body))
            parts = path.split("/")
            if method == "POST" and len(parts) == 4 and parts[0] == "Projects" and parts[2:] == ["Tasks", "bulk"]:
                if self.project(who, parts[1]) is None:
                    return None
                if not isinstance(body, list) or not all(isinstance(b, dict) and isinstance(b.get("attributes"), dict)
                                                         for b in body):
                    return self.send(400, {"error": "send a list of {ParentID, attributes}"})
                made = [self.add(fake.data["tasks"].setdefault(parts[1], []), b["attributes"]) for b in body]
                for m, b in zip(made, body):
                    m["parentId"] = b.get("ParentID")
                return self.send(201, {"data": made})
            if method == "POST" and len(parts) == 3 and parts[0] == "Ideas" and parts[2] == "Stage":
                idea = self.find(fake.data["ideas"], parts[1])
                if idea is None:
                    return None
                stage = (body or {}).get("Stage") if isinstance(body, dict) else None
                if not isinstance(stage, int) or not 0 <= stage <= 5:
                    return self.send(400, {"error": "Stage must be 0 to 5"})
                if stage < idea["attributes"].get("Stage", 0):
                    return self.send(400, {"error": f"An idea can't move back from stage {idea['attributes']['Stage']} "
                                                    f"to {stage}"})
                idea["attributes"]["Stage"] = stage
                return self.send(200, {"data": idea})
            target = self.target(who, parts)
            if target is None:
                return None
            if method == "POST":
                if not isinstance(target, list):
                    return self.send(405, {"error": "POST makes new records; PATCH changes them"})
                attrs = body.get("attributes") if isinstance(body, dict) else None
                if not isinstance(attrs, dict) or not attrs.get("Name"):
                    return self.send(400, {"error": "attributes.Name is required"})
                made = self.add(target, attrs)
                if parts == ["Ideas"] and query.get("challengeId"):
                    made["challengeId"] = query["challengeId"][0]
                return self.send(201, {"data": made})
            if isinstance(target, list):
                return self.send(405, {"error": "PATCH needs a record's ID"})
            updates = body.get("updates") if isinstance(body, dict) else None
            if not isinstance(updates, dict) or not updates:
                return self.send(400, {"error": "send the changes under updates"})
            if target.get("sourceType") == "Jira":
                return self.send(400, {"error": "Tasks synced from Jira are read-only in PPM Express"})
            target["attributes"].update(updates)
            return self.send(200, {"data": target})

        def add(self, rows, attrs):
            made = {"id": str(uuid.uuid4()), "attributes": dict(attrs)}
            rows.append(made)
            return made

        def find(self, rows, rid):
            found = [r for r in rows if r["id"] == rid]
            if not found:
                self.send(404, {"error": "no such record"})
                return None
            return found[0]

        def target(self, who, parts):
            """The list to add to (a POST) or the record to change (a PATCH); None when an answer is sent."""
            if parts[0] == "Projects":
                if len(parts) == 1:
                    return fake.table("projects", who)
                project = self.project(who, parts[1])
                if project is None or len(parts) == 2:
                    return project
                kind = {"Tasks": "tasks", "KeyDates": "key_dates"}.get(parts[2])
                if kind is None:
                    self.send(404, {"error": "not found"})
                    return None
                rows = fake.data[kind].setdefault(parts[1], [])
                return rows if len(parts) == 3 else self.find(rows, parts[3])
            if parts[0] in SHARED and len(parts) <= 2:
                rows = fake.table(SHARED[parts[0]], who)
                return rows if len(parts) == 1 else self.find(rows, parts[1])
            self.send(404, {"error": "not found"})
            return None

    return Handler


def start(port=0, host="127.0.0.1"):
    """Start a fake in a background thread: (server, fake state, base URL)."""
    fake = Fake()
    server = ThreadingHTTPServer((host, port), make_handler(fake))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, fake, f"http://{host}:{server.server_address[1]}{PREFIX}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=18080)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv, _, url = start(a.port, a.host)
    print(f"fake PPM Express at {url}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
