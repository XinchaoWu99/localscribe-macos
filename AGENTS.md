# LocalScribe Agent Rules

This file applies to the whole `localscribe` project.

## Required close-out after every meaningful change

After any improvement, refactor, or bug fix:

1. Run a quick whole-project review, not just a single-file check.
2. Look for obvious regressions, stale assumptions, and user-facing wording drift.
3. Check whether any generated or unnecessary files were created and remove them if they are safe to delete.
4. If an apparent bug is discovered during the review, fix it in the same pass when feasible instead of leaving it behind.

## Review checklist

- Run the relevant automated checks first, then the broader suite if the change touches shared behavior.
- Review both backend and frontend impact when a feature crosses the API boundary.
- Re-check tests and tooling that may encode old product behavior after UX or workflow changes.
- Prefer fixing small adjacent defects immediately when they are clearly in scope.

## Safe cleanup expectations

Delete generated junk when it appears in the repo workspace, including:

- `__pycache__/`
- `.pytest_cache/`
- `test-results/`
- `playwright-report/`
- stray `.pyc` files
- other generated caches that are not source artifacts

Do not remove:

- checked-in docs, assets, fixtures, or release files
- user data under `.localscribe-data/` unless the task explicitly requires it
- dependency directories or lockfiles unless the change actually calls for it

## Bug handling

- Treat obvious broken behavior as part of the current task.
- Do not leave known failing tests, stale UI copy, or dead code paths behind if they can be fixed safely in the same change.
- If a bug cannot be fixed safely in the current pass, call it out explicitly in the final review notes with file references.
