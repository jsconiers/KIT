"""ppmx: a Model Context Protocol (MCP) server for PPM Express's public REST API. It reads portfolios,
programs, projects, tasks, key dates, deliverables, ideas, challenges, and resources, and creates and updates them
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

STATUS: confirmed on 02-Nov-2026. The endpoint paths (client.ENDPOINTS) match PPM Express's OpenAPI
description, and the reads, response shapes, and attribute names (tools.FIELDS) were checked against a
live tenant, read-only; the writes follow the description and are tested against tests/fake_ppmx.py.
The code tables (codes.TABLES) are the ones PPM Express publishes.
"""
__version__ = "0.3.0"
