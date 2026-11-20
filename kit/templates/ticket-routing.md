# Ticket routing map

Where tickets of each kind should go. The ticket watcher (`kit-tickets`, part of the morning brief when
TICKET_WATCH is on) flags an open ticket as misrouted when its title matches a rule below but its
assignment group isn't the group the rule names, and drafts a next step for you. Nothing is sent and no
ticket is changed.

Copy this file to `memory/context/ticket-routing.md` (or point TICKET_ROUTING_FILE at your copy) and
replace the examples with your own. Only the lines under "## Rules" are read.

- One rule per line: `- pattern, pattern -> Assignment group`.
- A pattern is a word or phrase matched whole, in any case. Wrap it in slashes for a regular expression:
  `- /postgres(ql)?/ -> Database - PostgreSQL` (one regular expression per line, no commas).
- The group is matched loosely: a ticket with "Database - SQL Server Team" satisfies "Database - SQL Server".
- The first rule that matches a ticket's title is the one used, so put the specific rules first.

## Rules

- SQL Server, MSSQL -> Database - SQL Server
- MySQL, MariaDB -> Database - MySQL
- /postgres(ql)?/ -> Database - PostgreSQL
- Active Directory, Group Policy, GPO -> Identity - Directory Services
- firewall rule, load balancer -> Network - Security
- certificate renewal, TLS certificate -> PKI - Certificates
