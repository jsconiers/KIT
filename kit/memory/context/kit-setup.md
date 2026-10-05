# Kit's setup

Installed on {{DATE}} on {{OWNER}}'s Mac.

- Kit's files are in `~/Claude/Agents/kit`, which only {{OWNER}}'s account can open.
- Kit loads in every Claude Code session through one import line in `~/.claude/CLAUDE.md`.
- Permission rules in `~/.claude/settings.json` let Kit update its memory, `QUEUE.md`, and
  `STATUS.md` without prompting. Claude Code asks {{OWNER}} before any edit to lessons,
  preferences, `KIT.md`, or Claude Code's own settings, and before risky commands.
- Claude Code's built-in auto memory stays on and keeps per-project notes; this `memory/`
  folder holds what applies across all of {{OWNER}}'s work.
- To take Kit out of Claude Code: `bash ~/Claude/Agents/kit/.install/uninstall.sh`. To put it
  back: `bash ~/Claude/Agents/kit/.install/install.sh`. Backups of the Claude Code settings
  files it changed are in `~/Claude/Agents/kit/.install/backups/`.
