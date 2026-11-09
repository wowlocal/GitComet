# Independent stock-versus-fix protocol review

Reviewed `PROTOCOL.md` before measurements. **The design can answer Havunen's framework-comparison request**, provided the metric selection and invalidation rules below are fixed before results are inspected. It does not isolate app draft #742, and is not a physical-trackpad feel experiment.

## Source identity checked

- GitComet A/B checkout is at `ad5df1d185c1a8805870bffcfde592d5e3ce355a`; its upstream manifest pins GPUI `c55d73659dd6560d3e70281056f841e6d366c0e5`.
- Locally verified that `c55d73659dd6560d3e70281056f841e6d366c0e5` is the merge base and ancestor of `aad11809345380e3ae2d79f6cfcfc5aaf2af4edc`.
- The latter adds exactly one commit, `fix(macos): pace native Metal windows with CAMetalDisplayLink`, touching nine files. This avoids an unrelated framework-history difference between conditions.
- Build identity and diagnostic parity remain execution checks: record the resolved dependency graph, common instrumentation patch hash, condition-specific framework source hash, compiler/toolchain, features, environment and signed binary hash. The application production diff must be empty between A and B apart from dependency selection. Neither condition may include app draft #742 or its momentum implementation.

## Controls already sound

Eight runs in A B B A B A A B order balance condition and simple order effects. Four runs per condition are the experimental replicates; thousands of frames are not thousands of independent runs. The copied profile, common absolute-schedule input, unchanged real session, fixed viewport/display, foreground witnesses, default frame policy, no simultaneous builds/AX/video/profilers, and whole-device energy scope are appropriate controls.

The matched release profile is essential. Warm-up should be a specified identical sequence in both conditions, with a recorded endpoint that resets the measured scroll to the same history position. Use a fresh copy of the same isolated profile per run; record the selected repository's HEAD/history identity so an external repository change cannot silently alter the scene. Warm-up iterations, measured packet schedule and final endpoints should be retained in the manifest.

## Predefine before running

1. **Exact primary interval selection.** Specify the measured scrolling window and whether both drawable presentation endpoints must lie inside it. Use unique successful `presentedTime > 0` records for the measured window. Preserve zero/did-not-present callbacks and their counts separately: skipping a submitted drawable can itself be an outcome. Do not silently replace them with callback timestamps. Keep an all-motion-window result even if an explicitly predefined high-motion subset is also useful.
2. **Thresholds and denominators.** Freeze the tolerance around 16.67/25/33.33 ms; otherwise normal timestamp rounding creates artificial exceedances. Report long-gap counts with measured duration or a per-second rate as well as interval counts, since a slower condition produces fewer presented intervals. Define the presentation-rate calculation and percentile convention. Keep maximum gaps and all per-run results.
3. **Pairing and aggregation.** Fix adjacent opposite-condition pairs `(1,2)`, `(3,4)`, `(5,6)`, `(7,8)` before analysis. Report the sign of B-minus-A consistently. Per-run median/range across four runs is descriptive; do not imply a tight statistical confidence interval or stable population effect from this small serial experiment.
4. **Invalidation versus outcomes.** Predeclare contamination reasons and retain every failed attempt, condition and reason. Lost focus, changed geometry, missing packets, trace overflow or a GPU error can invalidate a run. Slow presentation, skipped presentation, high GPU energy or ordinary dispatch lateness must not be discarded merely because they are unfavorable. If a fixed dispatch-lateness gate is necessary for replay validity, report its threshold and condition-specific failures; framework scheduling may itself affect dispatch timing. State that the planned input schedule is identical, and show actual dispatch-lateness distributions rather than assuming delivered timing was identical.

## Interpretation limits

Sample display mode, power source, Low Power Mode and available thermal/performance state before and after each run. Use identical Caffeinate settings throughout. This controls obvious policy changes without forcing an artificial GPU clock or refresh rate. OS adaptive scheduling and background composition may still vary; show that variation rather than silently subtracting it.

The shared 1 Hz observer is a reasonable compromise. Its directly attributable parent CPU should be reported. Child CPU includes the measured app and must not be added as extra observer overhead. Whole-device IOReport Energy Model Watts remain a modeled device-wide rate, including WindowServer and other GPU work. Accumulated IOKit GPU execution is a different counter from native command-buffer start/end duration or peak-compute utilization.

Equal instrumentation is necessary but not proof of zero instrumentation effect. Both binaries must be called **instrumented release builds**, with diagnostics disabled by default, and the synthetic workload described plainly. The final conclusion should be limited to this source, display, workload and observed run-to-run range. A remaining physical-trackpad feel question needs separate evidence.

No source changes, build, app interaction, process mutation or publication was performed by this reviewer.

## Pre-result cadence-window clarification review

Reviewed the appended definitions and `input-plan.json` before any A/B runtime data was available. Selecting high-motion cores from the already fixed input packets is acceptable: the selection depends on the source workload, not on which build produces favorable frames. Excluding an intentional 553.837 ms packet gap avoids misclassifying a demand-driven idle period as a dropped frame.

Independently reproduced the two core ranges, **56,906–645,953 µs** and **1,811,652–2,372,904 µs**, using the declared >120 ms split, first/last absolute delta ≥4 px and 50/20 ms trims. They provide **1.150299 s per cycle**, or **4.601196 s across four measured cycles**. They include 140/240 source packets and 87.7% of absolute displacement, but only 39.2% of the full 2.932084 s plan timeline. The primary conclusion must therefore describe sustained high-motion cadence. Low-speed tails, starts, stops and full-phase cadence remain separate descriptive outcomes; this is not evidence that every part of a glide improved.

Anchoring the fixed offsets to the first actual dispatch is a consistent alignment rule. Keep first-dispatch delay and packet lateness visible separately, since this alignment does not measure end-to-end input latency. Do not re-anchor each core to a favorable rendered position or shift its end after inspecting frames.

Two definitions need numerical/editorial consistency before runtime analysis:

- The protocol's stated 0.25 ms tolerance does not equal its first listed 17 ms cutoff: 16.67 + 0.25 = **16.92 ms**. Using exact nominal periods instead gives **16.916667, 25.25 and 33.583333 ms**. Freeze one explicit convention and use it in both prose and code.
- Rename the earlier “Primary measured window” to “full-phase window,” since the later clarification makes source-active cores primary for cadence and retains the full phase for power/CPU.

Pairing only timestamps within each core necessarily censors intervals at core edges. Keep every planned core in the exposure and presentation-rate denominator, including a core with few or zero successful presentations. Report per-core presentation counts; do not discard sparse cores or claim smoothness from conditional interval quantiles alone. Full-phase data should retain long gaps crossing core boundaries, with intentional pauses clearly labelled. These safeguards prevent the new windowing rule from hiding a stall that spans a core boundary.

Input-plan SHA-256 at review: `3ab76a1962320ac20f7097dcb91d85c0b8e35ee4764ef06cbeae27ed6e9e51b3`.
