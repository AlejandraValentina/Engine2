# AGENTS.md

## Non-negotiable rules
- Defaults intact: all new behavior is opt-in; if flags are off, outputs and schemas remain unchanged.

## Mandatory gates (exact commands)
- `python3 -m pytest -q`
- `python3 -m pytest -q -W error::RuntimeWarning`
- `python3 -m pytest -q -m integration`
- `python3 -m pytest -q -m system`
- `python3 -m pytest -q -m legacy`

## Reports and schemas
- Knock report schema: `schemas/knock_report.schema.json`
- Legacy golden regression datasets: `benchmarks/datasets/regression_golden/legacy_compat/`

## GUI offscreen
- Run GUI tests/headless exports with `QT_QPA_PLATFORM=offscreen`.

## Runtime guidance
- Target `python3 -m pytest -q -m integration` runtime: <120s (optimize tests only; do not change core).
