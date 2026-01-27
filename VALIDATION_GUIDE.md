# VALIDATION_GUIDE

A) Default repo suite (must be green)
- `python -m pytest -q`

B) Warnings strict
- `python -m pytest -q -W error::RuntimeWarning`

C) Fast dev loop
- `python -m pytest -q -m "not slow"`

D) Pro dyno focus
- `python -m pytest -q -W error::RuntimeWarning -k pro_dyno`

Notes
- 2026-01-27: Updated integration baseline bands (BMEP/VE/HP) to reflect current 0D calibration with valve-area penalty and revised friction scaling. Adjusted expectations document the new steady-state outputs without changing default feature flags.
