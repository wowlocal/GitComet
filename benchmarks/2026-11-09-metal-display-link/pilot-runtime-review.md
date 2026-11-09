# Independent pilot runtime review

**No arithmetic/control blocker to starting the balanced eight-run series was found. All pilots remain excluded from comparison replicates.**

Reviewed the valid stock pilot `pilot-stock-20261109-202842` and unchanged-source valid fixed pilot `pilot-fixed-20261109-203131` directly from their measurement, frame, native timing and analysis records. The failed fixed startup attempt `pilot-fixed-20261109-202952` remains retained with its focus/readiness failure and missing-plan/capture consequences. It is not a numeric comparison result.

Both valid pilots have:

- Identical frozen profile, packet plan, selected-repository HEAD/status/index identity, 264 runtime repositories and one loaded repository.
- Matching history viewport `[243,117,1095,882]`, window bounds, built-in 120 Hz display, 2× scale, AC power, Low Power Mode off and thermal state 0 at both environmental snapshots. Ready and after-scroll snapshots identify the measured app as foreground.
- All twelve before/after witnesses alternating 2,000/5,468 px, 1,442 app inputs, 1,440 native packet markers with the declared signs/deltas, and **all 960 measured input stages**.
- Maximum absolute CA/Unix mapping residuals of **0.118 ms** and **0.181 ms**, respectively. Core windows use direct native marker times rather than this cross-clock mapping.
- All eight planned cores and **4.601196 seconds** of exposure. Independently reproduced presentation counts/rates, median, p95, p99 and long-gap counts. `statistics.quantiles(..., method='inclusive')` reproduces the analyzer's percentile results.
- Contiguous telemetry samples, matching summed interval and endpoint durations, nondecreasing per-process GPU counters, and independently reproduced energy, CPU and GPU rates. GPUPH residency totals agree with phase wall durations.
- Complete 50-second native captures, zero dropped records, zero missing presentation/GPU callbacks and zero GPU completion errors. The scheduled recorder flush falls **4.47/4.53 seconds after the idle-after window**, respectively, so it does not contaminate that window.

The fixed pilot's **365 zero/did-not-present outcomes** are retained correctly. They are not missing records or GPU errors, and must not be removed as contamination or used to retune the frozen analysis. The pilot presentation rates differ; that is a reason to collect the planned balanced replicates, not a conclusion from these pilots.

Machine-readable details and raw artifact hashes are in `pilot-runtime-review.json`. No UI, build, live profiling or process changes were performed by this reviewer. Independent calculations were small Python operations on saved files.
