#!/usr/bin/env python3
"""fake_ppmx: a stand-in for PPM Express's public API, for the PPM Express MCP server's tests and the
container smoke test. People with their own tokens see different projects, so a test can tell one caller's
data from another's. The paths, shapes, and scopes follow PPM Express's OpenAPI description (lowercase
paths; lists as {"data": [...]} with no paging; records as {"id", "attributes", ...}; people fields as
lists of {"id", "fullName", "imageId"}; Portfolio and Program as lists of {"id", "name"}; /me without a
name), as confirmed against a live tenant on 02-Nov-2026. Coded fields come back as numbers. Writes work
the way the API describes: POST {"attributes": {...}} to create (a sub-task adds "parentId"), PATCH
{"updates": {...}} to change, POST {"stage": "Active"} to move an idea. Each fake has its own copy of the
data, so one test's writes never leak into another's.

  python3 tests/fake_ppmx.py [--port 18080]     serve http://127.0.0.1:PORT/@test/v1.0 until stopped

Tokens: token-alex-0001 (Alex: read and write scopes; users/{id} gives Alex's full name), token-blake-0002
(Blake: project:read only, so a change gets 403 and users/{id} 403), token-busy-0003 (answers 429 once per
path, then like Alex), token-lost-0004 (like Alex, but a change is recorded and then lost, and the reply
isn't JSON, so the caller can't confirm it), token-carol-0005 (Carol: resource:read, but PPM Express shows
her no resources, ideas, or challenges, as a live tenant did). Anything else gets 401.
"""
import argparse
import copy
import json
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREFIX = "/@test/v1.0"
TOKENS = {"token-alex-0001": "alex", "token-blake-0002": "blake", "token-busy-0003": "busy",
          "token-lost-0004": "lost", "token-carol-0005": "carol"}
U_ALEX, U_BLAKE, U_CAROL = ("50000000-0000-4000-8000-000000000001", "50000000-0000-4000-8000-000000000002",
                            "50000000-0000-4000-8000-000000000003")
ME = {"alex": {"id": U_ALEX, "logonAccount": "arivera@example.com", "email": "arivera@example.com"},
      "blake": {"id": U_BLAKE, "logonAccount": "blake.chen@example.com", "email": "blake.chen@example.com"},
      "carol": {"id": U_CAROL, "logonAccount": "carol@example.com", "email": "carol@example.com"}}
USERS = {U_ALEX: {"id": U_ALEX, "fullName": "Alex Rivera", "email": "arivera@example.com"}}
READ_WRITE = [f"{e}:{m}" for e in ("project", "task", "keydate", "deliverable", "resource", "idea", "challenge",
                                    "portfolio", "program") for m in ("read", "write")] + ["user:read"]
SCOPES = {"alex": READ_WRITE, "blake": ["project:read", "task:read", "deliverable:read"],
          "carol": ["project:read", "resource:read", "idea:read", "challenge:read"]}

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
D1, D2, D3 = ("80000000-0000-4000-8000-000000000001", "80000000-0000-4000-8000-000000000002",
              "80000000-0000-4000-8000-000000000003")
I1, I2 = "70000000-0000-4000-8000-000000000001", "70000000-0000-4000-8000-000000000002"
R1, R2, R3 = ("60000000-0000-4000-8000-000000000001", "60000000-0000-4000-8000-000000000002",
              "60000000-0000-4000-8000-000000000003")


def item(id_, **attributes):
    return {"id": id_, "attributes": attributes}


def person(id_, name):
    return {"id": id_, "fullName": name, "imageId": None}


# People fields hold resource IDs, which differ from user IDs (as on a live tenant), except where noted.
ALEX_R, SAM_R, BLAKE_R = person(R1, "Alex Rivera"), person(R2, "Sam Lee"), person(R3, "Blake Chen")
INFRA, DIGITAL, CLOUD = {"id": P2, "name": "Infrastructure"}, {"id": P1, "name": "Digital"}, {"id": G1, "name": "Cloud migration"}

# Codes as PPM Express publishes them. Status: 0 On Track, 1 At Risk, 2 Critical, 10 Done. Progress:
# 0 Not Started, 1 Completed, 2 In Progress. Key date type: 0 Key Date, 1 Milestone. Idea stage: 1
# Proposed, 2 Active.
DATA = {
    "portfolios": {"alex": [item(P1, Name="Digital", Manager=[ALEX_R], OverallStatus=0),
                            item(P2, Name="Infrastructure", Manager=[SAM_R], OverallStatus=1)],
                   "blake": [item(P1, Name="Digital", Manager=[ALEX_R], OverallStatus=0)]},
    "programs": {"alex": [item(G1, Name="Cloud migration", Manager=[SAM_R], Portfolio=[INFRA])],
                 "blake": []},
    "projects": {
        "alex": [item(A1, Name="Network refresh", OverallStatus=0, Manager=[ALEX_R], StartDate="2026-09-01T00:00:00",
                      FinishDate="2027-03-31T00:00:00", Portfolio=[INFRA], Program=[CLOUD],
                      Progress=2, Description="Replace the core switches."),
                 item(A2, Name="Data center exit", OverallStatus=2, Manager=[SAM_R], StartDate="2026-01-15T00:00:00",
                      FinishDate="2026-12-15T00:00:00", Portfolio=[INFRA], Program=[CLOUD],
                      Progress=2),
                 item(A3, Name="Mobile app", OverallStatus=0, Manager=[ALEX_R], StartDate="2026-11-01T00:00:00",
                      Portfolio=[DIGITAL], Progress=0)],
        "blake": [item(B1, Name="Payments upgrade", OverallStatus=1, Manager=[BLAKE_R],
                       StartDate="2026-08-01T00:00:00", FinishDate="2026-11-20T00:00:00", Portfolio=[DIGITAL])],
    },
    "tasks": {A1: [item(T1, Name="Order switches", Status=0, Progress=2, AssignedTo=[SAM_R], DueDate="2026-10-20T00:00:00"),
                   item(T2, Name="Design review", Status=10, Progress=1, AssignedTo=[ALEX_R], DueDate="2026-10-01T00:00:00"),
                   item(T3, Name="Cutover plan", Status=0, Progress=0, AssignedTo=[person(U_ALEX, "A. Rivera")],
                        DueDate="2026-11-12T00:00:00"),
                   {**item(T4, Name="Jira epic: firmware", Status=1, Progress=2, DueDate="2026-12-01T00:00:00",
                           AssignedTo=None), "sourceType": "Jira", "parentId": None, "rank": 4}],
              B1: [item("f0000000-0000-4000-8000-000000000005", Name="Card vault review", Status=0, Progress=0,
                        AssignedTo=[BLAKE_R], DueDate="2026-11-05T00:00:00")]},
    "key_dates": {A1: [item(K1, Name="Design approved", Date="2026-10-01T00:00:00", Type=0, Status=10, IsComplete=True),
                       item(K2, Name="Go-live", Date="2026-11-30T00:00:00", Type=1, Status=0, IsComplete=False),
                       item(K3, Name="Vendor contract", Date="2026-10-15T00:00:00", Type=1, Status=1, IsComplete=False)]},
    "deliverables": {A1: [{**item(D1, Name="Switch design pack", Status=0, Progress=0.5, AssignedTo=[ALEX_R],
                                  DueDate="2026-11-06T00:00:00"), "sourceType": "Ppmx"},
                          {**item(D2, Name="Cabling survey", Status=10, Progress=1.0, AssignedTo=[SAM_R],
                                  DueDate="2026-10-10T00:00:00"), "sourceType": "Ppmx"}],
                     A3: [{**item(D3, Name="App store listing", Status=0, AssignedTo=[], DueDate="2026-12-01T00:00:00"),
                           "sourceType": "Ppmx"}]},
    "ideas": {"alex": [{**item(I1, Name="Self-service portal", Stage=1), "votes": 4},
                       {**item(I2, Name="AI triage", Stage=2), "votes": 9, "challengeId": C1}]},
    "challenges": {"alex": [item(C1, Name="Service desk of the future", Status=0)]},
    "resources": {"alex": [item(R1, Name="Alex Rivera", Email="arivera@example.com"),
                           item(R2, Name="Sam Lee", Email="sam@example.com")]},
}
FIELDS = {"Project": [{"key": "Name", "label": "Name", "type": "Text", "isMultiChoice": False, "isReadonly": False},
                      {"key": "OverallStatus", "label": "Overall Status", "type": "Choice", "isMultiChoice": False,
                       "isReadonly": False, "settings": {"options": [0, 1, 2, 10]}}],
          "Deliverable": [{"key": "Name", "label": "Name", "type": "Text", "isMultiChoice": False, "isReadonly": False},
                          {"key": "AssignedTo", "label": "Assigned To", "type": "Resource", "isMultiChoice": True,
                           "isReadonly": False}]}
SHARED = {"portfolios": "portfolios", "programs": "programs", "resources": "resources", "challenges": "challenges",
          "ideas": "ideas"}


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
            self.lost = who == "lost"
            if self.lost:
                who = "alex"
            return who, path, urllib.parse.parse_qs(url.query)

        # ---- reads
        def do_GET(self):  # noqa: N802
            got = self.who()
            if not got:
                return
            who, path, query = got
            parts = path.split("/")
            if path == "me":
                return self.send(200, {"data": {**ME[who], "integrations": {}, "token": {
                    "id": "t-1", "name": "kit", "expirationDate": "2027-01-31T00:00:00Z", "scopes": SCOPES[who]}}})
            if len(parts) == 2 and parts[0] == "users":
                if "user:read" not in SCOPES[who] or parts[1] not in USERS:
                    return self.send(403, {"errorMessage": "Access denied"})
                return self.send(200, {"data": USERS[parts[1]]})
            if path == "projects":
                return self.send(200, {"data": fake.table("projects", who)})
            if path in SHARED:
                rows = fake.table(SHARED[path], who)
                if path == "ideas" and query.get("challengeId"):
                    rows = [i for i in rows if i.get("challengeId") == query["challengeId"][0]]
                return self.send(200, {"data": rows})
            if len(parts) >= 2 and parts[0] == "projects":
                project = self.project(who, parts[1])
                if project is None:
                    return None
                if len(parts) == 2:
                    return self.send(200, {"data": project})
                kind = {"tasks": "tasks", "keydates": "key_dates", "deliverables": "deliverables"}.get(parts[2])
                if kind and len(parts) == 3:
                    return self.send(200, {"data": fake.data[kind].get(parts[1], [])})
                if kind and len(parts) == 4:
                    found = self.find(fake.data[kind].get(parts[1], []), parts[3])
                    return None if found is None else self.send(200, {"data": found})
            if len(parts) == 2 and parts[0] == "fields":
                return self.send(200, {"data": FIELDS.get(parts[1], [])})
            if path == "redirect":                    # a client must not follow this with the token
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
            if not any(s.endswith(":write") for s in SCOPES[who]):
                return self.send(403, {"error": "the token has no write scope"})
            with fake.lock:
                fake.writes.append((who, method, path, body))
            if self.lost:                               # taken, then lost; the reply is a gateway's page
                page = b"<html>502 Bad Gateway</html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                return None
            parts = path.split("/")
            if method == "POST" and len(parts) == 3 and parts[0] == "ideas" and parts[2] == "stage":
                idea = self.find(fake.table("ideas", who), parts[1])
                if idea is None:
                    return None
                order = ["Draft", "Proposed", "Active", "Selected", "NotSelected", "Archived"]
                stage = (body or {}).get("stage") if isinstance(body, dict) else None
                if stage not in order:
                    return self.send(400, {"errorMessage": "stage must be one of " + ", ".join(order)})
                if order.index(stage) < idea["attributes"].get("Stage", 0):
                    return self.send(400, {"errorMessage": f"An idea can't move back from stage "
                                                           f"{order[idea['attributes']['Stage']]} to {stage}"})
                idea["attributes"]["Stage"] = order.index(stage)
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
                if body.get("parentId"):
                    made["parentId"] = body["parentId"]
                if parts == ["ideas"] and query.get("challengeId"):
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
            if parts[0] == "projects":
                if len(parts) == 1:
                    return fake.table("projects", who)
                project = self.project(who, parts[1])
                if project is None or len(parts) == 2:
                    return project
                kind = {"tasks": "tasks", "keydates": "key_dates", "deliverables": "deliverables"}.get(parts[2])
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
