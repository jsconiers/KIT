# Audit setup

What the auditor and `kit-audit` use. The auditor reads this before every job, so keep it
current.

- **Audit folder:** not set. Where the connector guard writes its monthly logs, usually `audit/`
  in the library root. It should match `audit_dir` in `connector-guard.json`.
- **Reports:** not set. Where the auditor saves its weekly reports, usually
  `<library root>/audit/reports/`.
- **Reviewers:** not set. Who reads the audit reports, by role.
- **Working hours:** not set. Write them as a time range and days, for example 07:00-19:00
  Mon-Fri. Until then, `kit-audit` uses 07:00 to 19:00, Monday to Friday.
- **Allowed callers:** optional. `kit-audit` takes them from `connectors.md`: the gateway and its
  direct callers. To override, add a bullet holding allowed_callers, a colon, and the agent names
  separated by commas, all in backticks.
- **Thresholds:** `kit-audit`'s defaults. Change a number here to override it.
  - `baseline_days: 30` days of history the volume checks compare against.
  - `volume_factor: 3` a day's calls or data above this many times the baseline daily average.
  - `volume_min_calls: 20` the fewest calls that can count as a spike.
  - `min_baseline_days: 5` active days of history needed before the volume checks run.
  - `result_bytes_max: 1000000` one result larger than this, in bytes.
  - `result_factor: 10` one result larger than this many times the baseline median.
  - `stale_days: 14` days with no new log lines, while connectors are configured.
  - `repeat_minutes: 60` a call to the same connector this soon after a failure is a repeat.
  - `open_session_hours: 2` sessions newer than this may still be running.
