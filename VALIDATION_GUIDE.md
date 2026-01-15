# VALIDATION_GUIDE

A) Default repo suite (must be green)
- `python -m pytest -q`
- `python -m pytest -q -W error::RuntimeWarning`
- `python -m pytest -q -W error::RuntimeWarning -k pro_dyno`

B) Fast local loop (optional)
- `python -m pytest -q -m "not slow"`

C) Extended integration/perf bands (expected failing until calibration workstream)
- `python -m pytest -q -m "integration or legacy"`
- `python -m pytest -q -m integration`
- `python -m pytest -q -m legacy`

Integration/perf band tests are tracked but may fail until legacy calibration is performed.
