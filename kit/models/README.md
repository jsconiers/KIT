# Per-agent model files

Optional. A file here named `<agent>.json` sets that agent's profile and wins over the `agents` map
in `../models.json`. For example, `meeting-scribe.json`:

```json
{
  "profile": "standard",
  "tasks": {"summarize-public": "local"}
}
```

`profile` is one of the profiles in `models.json` (deep, standard, fast). The `tasks` map is kept
for phase 2, when a named kind of task can go to a different profile; Claude Code picks one model
per agent, so phase 1 records it and doesn't use it.

After adding or changing a file, run `kit-models check`, then `kit-models apply`, then install the
agents with `python3 ~/Claude/Agents/kit/.install/shared/doctor.py --fix-agents`.

## Phase 2 and 3: calling models directly

`kit-delegate` (phase 2) and `kit-run` (phase 3, experimental) call providers' APIs themselves
instead of going through Claude Code. They read the same `models.json`, with these extra rules:

- **enabled_phase.** Shipped as `1`: only Claude is reachable. Set `"enabled_phase": 2` to allow
  the providers marked `"phase": 2` (an approved API, a local model).
- **Data class.** Every request is public, internal, or confidential (default internal). A provider
  takes data up to its `max_data_class` (Anthropic: confidential; others: public unless set), and
  non-Claude providers are also capped by `org_profile.non_claude_max_data_class` (shipped as
  public). Internal or confidential work never leaves Claude unless the org profile allows it.
- **Organization profile.** `org_profile.allowed_providers`, when set, is the list of providers
  anything may use.
- **Fallback.** A refused profile falls back along its `fallback` chain, then `default_profile`,
  ending in a Claude profile; `kit-run --no-fallback` refuses instead.
- **Credentials** are named, never stored: a provider's `credential_env` (an environment variable)
  or `keychain_entry` (a macOS Keychain entry), read at call time. Local providers need none
  (`"credential_required": false`). The Anthropic provider uses `ANTHROPIC_API_KEY` by default for
  direct calls; Claude Code's own sign-in isn't used by these tools.
- **Prices**, optional, per profile: `"usd_per_mtok": {"input": N, "output": N}` lets kit-cost show
  a cost for direct calls; without it, tokens are recorded and the cost is left empty.

Provider kinds: `anthropic`, and the OpenAI-compatible family: `openai`, `openai-compatible`,
`azure-openai` (set `base_url` to the resource, `api_version`, and use the deployment name as the
model), `ollama`, `lmstudio`, `vllm`, `litellm`. Each takes `base_url`, `timeout_seconds`, and an
optional `model_ids` map from a profile's model name to the provider's.

See `.install/shared/KIT-RUN.md` for kit-delegate and kit-run usage and limits.

## The eval gate

Don't move an agent off the default profile on judgment alone. First run its evaluation cases on
the new profile, and change models.json only if they pass:

```
kit-evals <agent>                                  # static checks, free
kit-evals --live <agent> --profile standard        # shows the estimated cost, runs nothing
kit-evals --live <agent> --profile standard --yes  # runs the cases through Claude Code
```

Then set the agent's profile in models.json (or `models/<agent>.json`), run `kit-models apply`,
and install the agents. Cases live in `tests/evals/<agent>.json`; an agent without cases can't
pass the gate, so write its cases first. The same rule applies to non-Claude profiles once phase 2
is on, and to kit-run.
