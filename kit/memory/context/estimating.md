# Estimating setup

What the PMO estimator uses. It reads this before every job, so keep it current.

- **Past project data:** not set. Where past projects' estimates and actuals live, such as the
  library's project folders, the demand register (`demands/REGISTER.md` in the library root), a
  past-projects sheet, or working folders. Actuals in an outside system, such as issue-tracker work
  logs, come through Kit.
- **Phase model:** not set. Your project life cycle's phases. Until set, the estimator uses intake,
  assessment, design, build, test, cutover, and closeout.
- **Roles:** not set. The roles to estimate effort for, such as architect, project manager,
  engineer, and tester.
- **Calibration notes:** none yet. Patterns from past estimates against actuals, such as phases that
  usually run over, and anything that makes a project an outlier.
- **Estimates:** `artifacts/<project>/estimates/` in the library root.
