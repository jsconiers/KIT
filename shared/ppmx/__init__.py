"""ppmx: a Model Context Protocol (MCP) server for PPM Express's public REST API. Read-only.

One package, two ways to run it:

  stdio  Kit's own connector on a laptop: `kit-ppmx serve` (or `python -m ppmx stdio`), with the
         owner's personal access token from the environment (or, on a Mac, the Keychain).
  http   A standalone service for a container platform such as OpenShift (Streamable HTTP,
         stateless): `gunicorn ppmx.server_http:application`. Every caller sends their own personal
         access token with each request; the server never stores or logs it.

Standard library only (the container adds gunicorn to serve HTTP). See README.md.

STATUS: stub. The endpoint paths (client.ENDPOINTS), the attribute names (tools.FIELDS), and the code
tables (codes.TABLES) follow PPM Express's published API description and still need checking against a
tenant's own endpoint reference (PPM Express > Automation > Swagger) before live use.
"""
__version__ = "0.1.0"
