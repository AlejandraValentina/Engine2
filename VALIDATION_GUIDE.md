# VALIDATION_GUIDE

A) Default repo suite (must be green)
- `python -m pytest -q`

B) Warnings strict
- `python -m pytest -q -W error::RuntimeWarning`

C) Fast dev loop
- `python -m pytest -q -m "not slow"`

D) Pro dyno focus
- `python -m pytest -q -W error::RuntimeWarning -k pro_dyno`
