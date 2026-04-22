# External Audit Triage

This note classifies externally reported findings using only evidence available in project documentation, code, and tests. Items are not treated as confirmed bugs unless they are backed by code paths, docs, or reproducible tests.

## Confirmed

| Finding | Evidence | Action in this iteration |
|---|---|---|
| `ve_actual` is semantically different in v1 and v2 | `core/thermo.py` computes v1 `ve_actual` from a modeled VE estimate; `core/advanced/orchestrator.py` reports v2 `ve` from trapped-mass based output; `tests/integration/test_pro_dyno_v2_ve_behavior.py` already treats them as comparable-but-not-identical | clarify docs and keep the comparison framed as trend-level, not identity |
| Junction/plenum nodes are 0D capacitance/mixing approximations, not full 1D resolved junction physics | `docs/TECHNICAL_SPECS_V2.md`, `core/advanced/junctions.py`, `core/advanced/plenum_cv.py`, and unit tests explicitly model 0D reservoirs and algebraic mixing | document physical limits more explicitly |
| Combustion tuning parameters are real but under-explained in public docs | `core/engine_components.py` exposes `burn_duration_*`, `ca50_*`, `wiebe_a/m`, and `combustion.wiebe.eta_scale`; public docs were thinner than internal docs | expose these controls more clearly in public/technical docs |
| Selfcheck is not the same thing as external validation and is partly range/golden-oriented | `pywavedyn.cli.run_selfcheck`, `validation_cases/expectations.json`, README, and validation docs show deterministic ranges/relations, while regression-golden is handled separately in benchmark datasets | document scope/limits and add explicit physical invariants to selfcheck output |
| Silent drift risk from opt-in flags/defaults is real enough to deserve explicit guardrails | multiple opt-in features in `docs/TECHNICAL_SPECS_V2.md`; existing tests `*_defaults_no_change.py`, `test_cli_mode_v1_unchanged_defaults.py`, `test_legacy_compat_golden_regression.py` show this is an active compatibility concern | document default/legacy policy more explicitly |
| Thermal model validity in pulsating flow is limited | `docs/TECHNICAL_SPECS_V2.md` describes a lumped wall model with Dittus-Boelter or constant-h; tests cover trend/sanity but not broad validity envelopes | document that it is a coarse trend/stability model, not a calibrated phase-resolved pulsating HTC model |

## Partially Confirmed

| Finding | Evidence | Interpretation |
|---|---|---|
| Selfcheck is “too golden-based” | selfcheck itself is not benchmark-golden; however project validation messaging could blur selfcheck, benchmarks, and regression-golden | partially confirmed as a documentation/scope clarity issue, not as a code bug |
| Tests for global physical invariants are weak | the suite already has many finite/conservation/monotonic/default-no-change tests, but they are spread out and selfcheck did not surface a compact invariant layer | partially confirmed; gap is integration/visibility more than total absence |
| Drift from defaults/flags could be silent | several no-op/default tests exist, but policy was not stated clearly enough in user-facing docs | partially confirmed as a documentation and regression-detection concern |

## Not Confirmed

| Finding | Evidence status | Interpretation |
|---|---|---|
| Parameters specifically named `k_dur` and `k_eta` are hidden or broken | those exact names do not appear in code; the implemented controls are `burn_duration_rpm_factor`, `burn_duration_load_factor`, `ca50_*`, and `wiebe.eta_scale` | not confirmed as stated; map to existing parameter names instead |
| A concrete numerical validity band for wall thermal in pulsating flow is known and undocumented | no source in code/tests/docs establishes a validated envelope with numeric bounds | not confirmed; document as an open limitation instead of inventing thresholds |
| Junction 0D behavior is a confirmed solver bug | current evidence supports “model limitation / approximation” rather than a specific bug | not confirmed as bug |

## Open Follow-up

- Add more explicit v2-specific physical invariant/system tests if future work needs stronger guarantees beyond current unit-level conservation checks.
- Validate whether any public material still overstates external fidelity for opt-in thermal/junction models after this doc pass.
