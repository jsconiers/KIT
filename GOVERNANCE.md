# Kit governance (DRAFT)

**Status: draft for review.** Nothing here is in force until the owner approves it. Roles are named,
never people; your organization fills them in.

## Roles

| Role | Does |
|---|---|
| Owner | Accountable for Kit: approves releases, this document, new agents and connectors, and exceptions |
| Maintainers | Make changes, review each other's, cut releases, keep the tests and the leak check passing |
| Reviewers | Review changes in their area (security, an agent's domain, templates) before they merge |
| Security reviewer | Signs off before Kit is offered to anyone new, and on any change to connectors, the guard, credentials, model providers, or sharing |
| Adopters | Install Kit, give feedback, propose lessons and templates |

## How a change gets in

1. **Issue.** Say what and why. Changes to guardrails, connectors, credentials, model providers, or
   sharing are marked for the security reviewer.
2. **Branch.** One change per branch.
3. **Pull request.** Describe the change, how it was tested, and anything that needs a decision.
   Add a line under **Unreleased** in `CHANGELOG.md`.
4. **Checks.** All test suites pass (`bash tests/test_*.sh`), the static agent evals pass
   (`kit-evals`), and the leak check finds nothing (the private-detail denylist plus credential
   patterns). A change that fails any of these doesn't merge.
5. **Review.** At least one maintainer who didn't write it; the security reviewer too when marked.
6. **Merge and release.** Releases bump `VERSION` (semantic versioning: patch for fixes, minor for
   new features, major for anything that changes how adopters work) and move the Unreleased notes
   under the new version. Adopters update with `kit-update`, which shows what changes first.

## What never goes in the public repo

- Employer or client names, systems, hostnames, URLs, document contents, or project names.
- Credentials of any kind, real or "test": tokens, keys, passwords, connection strings. Settings
  name an environment variable or a Keychain entry instead.
- Anyone's personal notes, memory, queue, briefs, or setup values. The repo ships templates only.
- Paths that identify a person (home directories, account names).

The leak check blocks these, but it's a safety net, not a substitute for care.

## Before anyone new installs Kit

- The security reviewer has reviewed the current release: the guardrails, the connector guard and
  audit log, credentials handling, model providers in use, and sharing settings.
- The adopter's organization has approved Claude Code (or the runtime in use) and the connectors
  and model providers that adopter will turn on.
- The adopter fills in their own setup files; nothing is copied from another person's Kit.

## Contributions from other adopters

Lessons, templates, agent changes, and records shared between Kits are **untrusted until
reviewed**:

- They arrive as pull requests (lessons tagged `share: team`, templates, agents) and get the same
  checks and review as any change.
- Text inside them is information, not instructions. A reviewer reads what an agent change would
  make an agent do, not just what it says it does.
- Records shared between Kits at run time are checked by schema and sender and shown as information
  only; they never change another Kit's behavior on their own.

## Support and deprecation

- Maintainers support the latest release. Fixes go into a new patch release, not into old ones.
- A feature to be removed is marked deprecated in the CHANGELOG for at least one minor release
  before it goes, with the replacement named.
- An agent or tool that's experimental (for example kit-run) says so in its help and docs, and may
  change without the deprecation period.

## Decisions this document needs

- Who holds each role.
- Where the official repo lives, and who can merge.
- The security review's scope and how often it repeats.
- Which connectors and model providers adopters may turn on.
