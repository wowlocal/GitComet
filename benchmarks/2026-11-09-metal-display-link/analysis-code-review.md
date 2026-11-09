# Pre-runtime measurement/analyzer review

Reviewed `run.py` and `analyze.py` before stock/fixed runtime measurements. No scripts, app sources, process state or UI were changed. Four small extracted-function fixtures ran entirely in Python memory; they are not performance measurements.

## Findings to resolve

1. **Telemetry can undercount energy after silently filtering a sample.** `analyze.py:24` removes rows lacking app CPU or a GPU PID, then `:27` sums each retained row's immediately preceding IOReport delta. If an interior row is removed, its energy interval disappears while endpoint elapsed time still spans it. A five-row fixture covering four seconds with one joule per interval and one missing interior CPU sample reports **0.75 W instead of 1 W**. Require contiguous selected indices and interval sums matching endpoint duration, or integrate SoC energy independently of per-process availability. Do not silently make the phase look cheaper.
2. **Intermediate GPU-counter resets can be hidden.** `analyze.py:31–32` checks only endpoint differences. Fixture values `100, 200, 20, 300, 400` contain a reset but report `counter_reset=false`. Check successive values and retain reset/missing process metrics explicitly without invalidating otherwise usable cadence data.
3. **Duplicate positive presentation timestamps inflate actual presentation rate.** `presentation_window` counts every record and inserts a zero-length gap when timestamps repeat. Fixture timestamps `0.2, 0.2, 0.3` report three presentations and intervals `[0, 100]` ms despite two unique presentation instants. Preserve raw duplicates as outcomes, but use unique timestamps for actual cadence/rate, with this convention explicit in the protocol.
4. **Empty/sparse cadence can crash condition aggregation.** Per-run `stats([])` correctly returns unavailable quantiles, but `stats([None, None])` raises `TypeError` at the condition summary. A run with no intra-core intervals is a meaningful result, not a reason to exclude it. Keep its fixed exposure and presentation rate, mark quantiles unavailable, and report per-metric replicate counts. Paired contrasts must likewise preserve an unavailable metric rather than subtract `None` or replace it with zero.
5. **Required matching controls are recorded without validation.** `run.py:132–136` verifies only one readiness record and twelve position records. It does not compare readiness viewport across runs, check position states/order, verify the alternating expected endpoint/delta, or enforce stable display/scaling/power witnesses. The declared workload should travel from the same prefill location through the same alternating 3,468-pixel net movements and return, within a fixed tolerance and without clamping. These need explicit checks before the series is accepted. `repository_identity()` also hashes HEAD and status names, but not the index identity named in the protocol.

## Scope clarification

`submission_outcomes` currently selects submissions by the full-phase window, while primary cadence uses eight cores that include some earlier/later time. Label those outcomes as full-phase, or additionally report outcomes for the core windows. Otherwise readers could assume its skipped/missing callback counts describe exactly the primary cadence exposure.

If a startup crash prevents `frames.jsonl` creation, post-run parsing outside the protected loop can fail before adding the attempt to the manifest. The partial directory remains, but recording the failed attempt and missing-file reason would fulfill the protocol's failure accounting more directly.

## Arithmetic that checks out

- Exact cutoff expressions now match nominal 120 Hz periods plus 0.25 ms.
- The per-core exposure is fixed and all eight cores, including empty ones, are retained.
- The interpolated quantile implementation is internally consistent and stated by its code.
- Six cycles ×240 packets align with 1,440 native `scenario_scroll` records; excluding the single prefill input makes `app_inputs[1:]` the correct alignment. Measured cycles start at native index 480; `app_inputs[481:]` selects their 960 application inputs.
- The common scenario observer logs `scenario_input` immediately before the native scenario marker, so the median CA-minus-Unix mapping is a sensible cross-clock mapping. Its residual distribution remains necessary evidence.
- Stage input `a` and `at_ms` share the operation-trace origin; `at_ms - a/1e6` is correctly dispatch lateness in milliseconds.
- Full-phase CPU/GPU/energy scopes, including drawable-acquisition time in the existing full submit probe, are distinguished from post-acquisition native submission timing.
- A/B pairing uses consistent fixed-minus-stock signs and run-level replicates, rather than pooling frames as independent experiments.

Runtime arithmetic and common-stock/fixed instrumentation equivalence still require the later artifact review.


## Follow-up review before pilots

Re-read the updated runner/analyzer and final protocol clarification. Prior arithmetic findings are addressed: unique actual presentation timestamps preserve duplicate counts; an interior missing counter makes telemetry unavailable; adjacent GPU counter resets are detected; sparse-core quantiles and paired missing metrics remain explicit. Re-ran the extracted-function static fixtures and all five checks passed. No app, runtime measurement or build was invoked.

The reset and prefill now produce 1,442 application input records: two setup inputs plus six ×240-packet plans. Pairing native packets with application inputs `[2:]`, and selecting measured application inputs `[482:]`, is correct. Twelve endpoint witnesses are checked against alternating 2,000/5,468 px positions; the repository index now has a hash; readiness viewport and normalized after-scroll display/window/power controls are compared across runs. Full-phase submission outcomes have an explicit scope label.

Moving recorder arming to the reset introduced a potential idle-after flush confound; the parent resolved it before runtime by extending capture to 50 seconds. With the declared schedule, replay ends near 32 seconds and idle-after spans about 34.5–44.5 seconds, before the flush at 50 seconds and normal scenario exit near 59 seconds. A per-loop game/build guard and missing-frame-file failure retention are now present. Their observer work is shared by both conditions and remains part of the reported observation overhead.

**No remaining blocking arithmetic finding for the planned pilots in this reviewed version.** Runtime review must still verify actual clock residuals, all 960 measured input stages, endpoint/viewport/environment witnesses, complete native capture, finite SoC data and residency-versus-wall consistency. The runner compares normalized environmental controls at the after-scroll snapshot; retain and inspect the ready snapshot as well rather than presenting this as continuous environmental monitoring. Thermal state is recorded, not forced.

The earlier individual findings remain above as review history, not unresolved defects in the latest scripts.
