"""Run the PPM Express MCP server.

  python -m ppmx stdio                    MCP on standard input and output, for one user; the token comes
                                          from the environment variable PPMX_TOKEN (or the one named in
                                          PPMX_TOKEN_ENV). Kit uses `kit-ppmx serve`, which can also read a
                                          Mac Keychain entry.
  python -m ppmx http [--host H] [--port P]
                                          the standalone server on the standard library's web server, for a
                                          local try (default 127.0.0.1:8080). In a container, gunicorn runs
                                          ppmx.server_http:application instead.
  python -m ppmx tools                    the tools it offers

Settings come from PPMX_* environment variables; see README.md.
"""
import argparse
import os
import socketserver
import sys
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server


class _ThreadingServer(socketserver.ThreadingMixIn, WSGIServer):
    daemon_threads = True


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):                     # the app writes its own audit lines
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m ppmx", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["stdio", "http", "tools"])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args(argv)

    from .tools import TOOLS
    if args.mode == "tools":
        for t in TOOLS:
            print(f"{t['name']:<18} {t['description']}")
        return 0
    if args.mode == "stdio":
        from .client import Client
        from .codes import load
        from .config import Settings
        from .mcp_core import Dispatcher
        from .server_stdio import serve
        from .tools import Context
        settings = Settings()
        client, tables = Client(settings), load(settings.codes_file)
        env_name = os.environ.get("PPMX_TOKEN_ENV") or "PPMX_TOKEN"
        hint = f"No personal access token: set the environment variable {env_name}."
        dispatcher = Dispatcher(lambda token: Context(client, settings, tables, token, hint=hint))
        return serve(dispatcher, lambda: os.environ.get(env_name, "").strip())
    from .server_http import make_app
    httpd = make_server(args.host, args.port, make_app(), server_class=_ThreadingServer,
                        handler_class=_QuietHandler)
    print(f"ppmx: serving MCP at http://{args.host}:{args.port}/mcp (Ctrl-C to stop)", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
