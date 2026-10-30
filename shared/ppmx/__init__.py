"""ppmx: a Model Context Protocol (MCP) server for PPM Express's public REST API. It reads portfolios,
programs, projects, tasks, key dates, ideas, challenges, and resources, and creates and updates them
(PPM Express's API has no delete). PPMX_WRITES=off makes it read-only.

One package, two ways to run it:

  stdio  Kit's own connector on a laptop, Mac or Windows, for Claude Code and Claude Desktop:
         `kit-ppmx serve` (or `python -m ppmx stdio`), with the owner's personal access token from the
         environment, the Mac Keychain, or Windows Credential Manager.
  http   A standalone service for a container platform such as OpenShift (Streamable HTTP,
         stateless): `gunicorn ppmx.server_http:application`. Every caller sends their own personal
         access token with each request; the server never stores or logs it.

Standard library only (the container adds gunicorn to serve HTTP). See README.md, and
openshift/INSTALL.md for the standalone service.

STATUS: stub. The endpoint paths (client.ENDPOINTS) and the attribute names (tools.FIELDS) follow PPM
Express's published API descriptions and still need checking against a tenant's own endpoint reference
(PPM Express > Automation > Swagger) before live use. The code tables (codes.TABLES) are the ones PPM
Express publishes.
"""
__version__ = "0.2.0"
