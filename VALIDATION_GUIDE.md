# VALIDATION_GUIDE

Canonical commands (must be green):
- `python -m pytest -q`
- `python -m pytest -q -W error::RuntimeWarning`
- `python -m pytest -q -W error::RuntimeWarning -k pro_dyno`
