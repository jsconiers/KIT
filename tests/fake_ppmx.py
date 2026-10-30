#!/usr/bin/env python3
"""fake_ppmx: a stand-in for PPM Express's public API, for the PPM Express MCP server's tests and the
container smoke test. Two people with their own tokens see different projects, so a test can tell one
caller's data from another's. The paths follow shared/ppmx/client.py's ENDPOINTS (provisional, as they
are), and coded fields come back as numbers, as PPM Express returns them.

  python3 tests/fake_ppmx.py [--port 18080]     serve http://127.0.0.1:PORT/@test/v1.0 until stopped

Tokens: token-alex-0001 (Alex), token-blake-0002 (Blake), token-busy-0003 (answers 429 once per path,
then like Alex). Anything else gets 401. Alex's project list comes back in two pages (nextLink).
"""
import argparse
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREFIX = "/@test/v1.0"
TOKENS = {"token-alex-0001": "alex", "token-blake-0002": "blake", "token-busy-0003": "busy"}
ME = {"alex": {"logonAccount": "alex", "email": "alex@example.com", "displayName": "Alex Rivera"},
      "blake": {"logonAccount": "blake", "email": "blake@example.com", "displayName": "Blake Chen"}}

P1, P2 = "aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002"
G1 = "bbbbbbbb-0000-4000-8000-000000000001"
A1, A2, A3 = ("cccccccc-0000-4000-8000-000000000001", "cccccccc-0000-4000-8000-000000000002",
              "cccccccc-0000-4000-8000-000000000003")
B1 = "dddddddd-0000-4000-8000-000000000001"
C1 = "eeeeeeee-0000-4000-8000-000000000001"


def item(id_, **attributes):
    return {"id": id_, "attributes": attributes}


PORTFOLIOS = {"alex": [item(P1, Name="Digital", Manager="Alex Rivera", OverallStatus=1),
                       item(P2, Name="Infrastructure", Manager="Sam Lee", OverallStatus=2)],
              "blake": [item(P1, Name="Digital", Manager="Alex Rivera", OverallStatus=1)]}
PROGRAMS = {"alex": [item(G1, Name="Cloud migration", Manager="Sam Lee", Portfolios=["Infrastructure"])],
            "blake": []}
PROJECTS = {
    "alex": [item(A1, Name="Network refresh", OverallStatus=1, Manager="Alex Rivera", StartDate="2026-09-01T00:00:00",
                  FinishDate="2027-03-31T00:00:00", Portfolios=["Infrastructure"], Programs=["Cloud migration"],
                  Progress=1, Description="Replace the core switches."),
             item(A2, Name="Data center exit", OverallStatus=3, Manager="Sam Lee", StartDate="2026-01-15T00:00:00",
                  FinishDate="2026-12-15T00:00:00", Portfolios=["Infrastructure"], Programs=["Cloud migration"],
                  Progress=1),
             item(A3, Name="Mobile app", OverallStatus=1, Manager="Alex Rivera", StartDate="2026-11-01T00:00:00",
                  Portfolios=["Digital"], Progress=0)],
    "blake": [item(B1, Name="Payments upgrade", OverallStatus=2, Manager="Blake Chen",
                   StartDate="2026-08-01T00:00:00", FinishDate="2026-11-20T00:00:00", Portfolios=["Digital"])],
}
TASKS = {A1: [item("f0000000-0000-4000-8000-000000000001", Name="Order switches", Status=1,
                   AssignedTo={"name": "Sam Lee", "email": "sam@example.com"}, DueDate="2026-10-20T00:00:00"),
              item("f0000000-0000-4000-8000-000000000002", Name="Design review", Status=2,
                   AssignedTo={"name": "Alex Rivera"}, DueDate="2026-10-01T00:00:00"),
              item("f0000000-0000-4000-8000-000000000003", Name="Cutover plan", Status=1,
                   AssignedTo={"name": "Alex Rivera"}, DueDate="2026-11-12T00:00:00"),
              {**item("f0000000-0000-4000-8000-000000000004", Name="Jira epic: firmware", Status=1,
                      DueDate="2026-12-01T00:00:00"), "sourceType": "Jira"}]}
KEY_DATES = {A1: [item("90000000-0000-4000-8000-000000000001", Name="Design approved", Date="2026-10-01T00:00:00",
                       Type=0, Status=2),
                  item("90000000-0000-4000-8000-000000000002", Name="Go-live", Date="2026-11-30T00:00:00",
                       Type=1, Status=1),
                  item("90000000-0000-4000-8000-000000000003", Name="Vendor contract", Date="2026-10-15T00:00:00",
                       Type=1, Status=1)]}
IDEAS = [{**item("70000000-0000-4000-8000-000000000001", Name="Self-service portal", Stage=1), "votes": 4},
         {**item("70000000-0000-4000-8000-000000000002", Name="AI triage", Stage=2), "votes": 9,
          "challengeId": C1}]
RESOURCES = [item("60000000-0000-4000-8000-000000000001", Name="Alex Rivera", Email="alex@example.com"),
             item("60000000-0000-4000-8000-000000000002", Name="Sam Lee", Email="sam@example.com")]
FIELDS = {"Project": [{"key": "Name", "label": "Name", "type": "Text", "isMultiChoice": False, "isReadonly": False},
                      {"key": "OverallStatus", "label": "Overall Status", "type": "Choice", "isMultiChoice": False,
                       "isReadonly": False, "settings": {"options": [1, 2, 3]}}]}


class Fake:
    """The fake's state: request counts per (user, path), and which busy paths have answered 429."""

    def __init__(self):
        self.hits = {}
        self.busy_done = set()
        self.lock = threading.Lock()

    def count(self, who, path):
        with self.lock:
            self.hits[(who, path)] = self.hits.get((who, path), 0) + 1


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

        def do_GET(self):  # noqa: N802
            auth = self.headers.get("Authorization") or ""
            who = TOKENS.get(auth[7:]) if auth.startswith("Bearer ") else None
            if not who:
                return self.send(401, {"error": "unauthorized"})
            url = urllib.parse.urlsplit(self.path)
            if not url.path.startswith(PREFIX + "/"):
                return self.send(404, {"error": "not found"})
            path = url.path[len(PREFIX) + 1:]
            query = urllib.parse.parse_qs(url.query)
            fake.count(who, url.path + ("?" + url.query if url.query else ""))
            if who == "busy":
                with fake.lock:
                    first = path not in fake.busy_done
                    fake.busy_done.add(path)
                if first:
                    return self.send(429, {"error": "slow down"}, [("Retry-After", "0")])
                who = "alex"
            parts = path.split("/")
            base = f"http://{self.headers.get('Host')}{PREFIX}"
            if path == "Me":
                return self.send(200, {"data": {"id": "50000000-0000-4000-8000-00000000000" + ("1" if who == "alex" else "2"),
                                                **ME[who], "token": {"id": "t-1", "name": "kit",
                                                "expirationDate": "2027-01-31T00:00:00Z",
                                                "scopes": ["Read Projects", "Read Resources"]}}})
            if path == "Portfolios":
                return self.send(200, {"data": PORTFOLIOS[who]})
            if path == "Programs":
                return self.send(200, {"data": PROGRAMS[who]})
            if path == "Projects":
                rows = PROJECTS[who]
                if who == "alex":                     # two pages, joined by a next link
                    if query.get("page") == ["2"]:
                        return self.send(200, {"data": rows[2:]})
                    return self.send(200, {"data": rows[:2], "nextLink": f"{base}/Projects?page=2"})
                return self.send(200, {"data": rows})
            if len(parts) >= 2 and parts[0] == "Projects":
                visible = {p["id"]: p for p in PROJECTS[who]}
                if parts[1] not in visible:
                    return self.send(404, {"error": "no such project"})
                if len(parts) == 2:
                    return self.send(200, {"data": visible[parts[1]]})
                if parts[2] == "Tasks":
                    return self.send(200, {"data": TASKS.get(parts[1], [])})
                if parts[2] == "KeyDates":
                    return self.send(200, {"data": KEY_DATES.get(parts[1], [])})
            if path == "Ideas":
                rows = IDEAS
                if query.get("challengeId"):
                    rows = [i for i in rows if i.get("challengeId") == query["challengeId"][0]]
                return self.send(200, {"data": rows})
            if path == "Resources":
                return self.send(200, {"data": RESOURCES})
            if len(parts) == 2 and parts[0] == "Fields":
                return self.send(200, {"data": FIELDS.get(parts[1], [])})
            if path == "Redirect":                    # a client must not follow this with the token
                return self.send(302, None, [("Location", "http://127.0.0.1:9/steal")])
            return self.send(404, {"error": "not found"})

    return Handler


def start(port=0, host="127.0.0.1"):
    """Start the fake in a background thread: (server, fake state, base URL)."""
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
