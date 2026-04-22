# AGENTS.md

## Role Of `docs/internal/`
- This folder mixes active internal guidance, evidence-heavy validation notes, audits, and historical planning.
- Treat it as support for current source-of-truth docs, not as an excuse to bypass code/tests.

## How To Read And Update Internal Docs
- Prefer these as current internal references:
- `FEATURES.md`
- `VALIDATION_GUIDE.md`
- `DOCUMENTATION.md`
- Treat these as historical, audit, or planning material unless explicitly refreshed:
- `AUDIT_REPORT.md`
- `EXTERNAL_AUDIT_TRIAGE.md`
- `VISION.md`
- `RELEASE_*`
- `TECHNICAL_DOCS.md`

## Non-Negotiable Documentation Rules
- Do not convert hypotheses from audits into confirmed defects without evidence in code, tests, or current public docs.
- If an internal doc is stale, mark it as legacy/historical or update it; do not silently let it compete with active guidance.
- When public docs and internal docs diverge, resolve the discrepancy instead of duplicating both stories.
- Keep internal updates compact, evidence-backed, and explicit about limits.
