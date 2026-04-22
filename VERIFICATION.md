# Verification

## Gate: `python3 -m pytest -q`
```
.................................ss..................................... [ 33%]
........................................................................ [ 67%]
.........................................s............................   [100%]
211 passed, 10 skipped, 77 deselected in 221.72s (0:03:41)
```

## Gate: `python3 -m pytest -q -W error::RuntimeWarning`
```
.................................ss..................................... [ 33%]
........................................................................ [ 67%]
.........................................s............................   [100%]
211 passed, 10 skipped, 77 deselected in 205.55s (0:03:25)
```

## Gate: `python3 -m pytest -q -m integration`
```
....................................................                     [100%]
52 passed, 7 skipped, 239 deselected in 89.31s (0:01:29)
```

## Gate: `python3 -m pytest -q -m system`
```
.....................                                                    [100%]
21 passed, 7 skipped, 270 deselected in 196.30s (0:03:16)
```

## Gate: `python3 -m pytest -q -m legacy`
```
..                                                                       [100%]
2 passed, 7 skipped, 289 deselected in 21.07s
```

## Gate: `python3 -m pytest -q -m integration --durations=20`
```
....................................................                     [100%]
============================= slowest 20 durations =============================
10.64s call     tests/integration/test_pro_dyno_v2_stable_mode.py::test_pro_dyno_v2_no_negative_at_low_rpm_when_stable_mode
6.44s call     tests/integration/test_autocalibration_reduces_error.py::test_autocalibration_reduces_error
5.20s call     tests/integration/test_full_network_runner_length_shifts_torque_peak.py::test_full_network_runner_length_shifts_torque_peak
5.01s call     tests/integration/test_pro_dyno_v2_positive_power.py::test_pro_dyno_v2_positive_power
4.91s call     tests/integration/test_pro_dyno_v2_stable_mode.py::test_pro_dyno_v2_marks_not_converged_points
4.74s call     tests/integration/test_pro_dyno_v2_indicated_positive.py::test_pro_dyno_v2_indicated_positive_when_combustion_on
4.58s call     tests/test_output_schema_full_scope.py::test_output_schema_full_scope
4.39s call     tests/integration/test_pro_dyno_v2_ve_behavior.py::test_pro_dyno_v2_ve_reasonable_and_trend
2.81s call     tests/integration/test_optimize_reduces_error.py::test_optimize_reduces_error
2.57s call     tests/integration/test_benchmark_report_schema_and_error_contract.py::test_benchmark_report_schema_and_error_contract
2.54s call     tests/test_output_schema_opt_report.py::test_output_schema_opt_report
2.43s call     tests/test_selfcheck_schema_validates.py::test_selfcheck_schema_validates
2.32s call     tests/integration/test_full_network_cross_talk_plenum.py::test_full_network_cross_talk_plenum
2.25s call     tests/test_headless_partload_map_generates_grid.py::test_headless_partload_map_generates_grid
2.24s call     tests/test_output_schema_calib_report.py::test_output_schema_calib_report
2.21s call     tests/test_output_schema_map.py::test_output_schema_map
2.17s call     tests/test_output_schema_selfcheck.py::test_output_schema_selfcheck
1.91s call     tests/integration/test_0d_1d_bidirectional_backpressure_affects_cycle.py::test_0d_1d_bidirectional_backpressure_affects_cycle
1.40s call     tests/integration/test_pro_dyno_v2_ve_behavior.py::test_v1_v2_ve_not_diverging_in_stable_point
0.43s call     tests/integration/test_0d_to_1d_scope.py::test_0d_to_1d_scope_signal
52 passed, 7 skipped, 239 deselected in 93.52s (0:01:33)
```

## Top 10 slowest (from durations)
1. 10.64s call     tests/integration/test_pro_dyno_v2_stable_mode.py::test_pro_dyno_v2_no_negative_at_low_rpm_when_stable_mode
2. 6.44s call     tests/integration/test_autocalibration_reduces_error.py::test_autocalibration_reduces_error
3. 5.20s call     tests/integration/test_full_network_runner_length_shifts_torque_peak.py::test_full_network_runner_length_shifts_torque_peak
4. 5.01s call     tests/integration/test_pro_dyno_v2_positive_power.py::test_pro_dyno_v2_positive_power
5. 4.91s call     tests/integration/test_pro_dyno_v2_stable_mode.py::test_pro_dyno_v2_marks_not_converged_points
6. 4.74s call     tests/integration/test_pro_dyno_v2_indicated_positive.py::test_pro_dyno_v2_indicated_positive_when_combustion_on
7. 4.58s call     tests/test_output_schema_full_scope.py::test_output_schema_full_scope
8. 4.39s call     tests/integration/test_pro_dyno_v2_ve_behavior.py::test_pro_dyno_v2_ve_reasonable_and_trend
9. 2.81s call     tests/integration/test_optimize_reduces_error.py::test_optimize_reduces_error
10. 2.57s call     tests/integration/test_benchmark_report_schema_and_error_contract.py::test_benchmark_report_schema_and_error_contract
