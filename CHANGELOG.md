# Changelog

## 0.2.0

- Consolidated the public README and visible docs surface around install, first result, validation, and docs index.
- Reduced initial GUI dyno surface by moving secondary controls behind an advanced section without removing export/report workflows.
- Added unit coverage for `core.knock`.
- Refreshed regression-golden benchmark datasets for Honda K20, Chevy 350, and single-cylinder moto with consistent metadata and regeneration scripts.
- Verified CLI smoke paths, benchmark contracts, selfcheck, docs consistency, build generation, and GUI export/offscreen tests.
- This release remains regression-golden focused; bundled benchmark datasets are simulator-vs-simulator baselines, not external dyno truth data.
