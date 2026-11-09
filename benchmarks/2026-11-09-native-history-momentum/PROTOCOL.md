# Same-binary native-momentum resampling trial

Registered before the new pilot/main run. This is a diagnostic experiment with programmatic replay of captured source metadata, not a physical-input or user-feel trial. Preserve all older artifacts. The root owns launch/acquisition; this reviewer owns these frozen metric definitions and analysis.

## Conditions and controls

Use the exact currently installed optimized GitComet binary at source commit `fe34d0636fe35af0ccbc693ce2b0861499a003c9`, identified by one SHA-256 checked before and after every run. Condition A sets `GITCOMET_HISTORY_MOMENTUM_RESAMPLING=off`, B sets it to `on`. The switch requires diagnostic opt-in and is cached once per process, so each run must launch a fresh process. All other app, GPUI, frame-rate, latency, settings, window, repository, source, and OS controls match. No new build is part of this comparison.

Run eight valid acquisition attempts in A B B A B A A B order (off,on,on,off,on,off,off,on). Predeclare adjacent pairs (1,2), (3,4), (5,6), (7,8), reporting on-minus-off contrasts. Every attempted startup and retry is retained. Pilots are separately marked and excluded. Ordinary high latency, nonpresented submissions, missing markers, effective source age, endpoint/path errors, GPU errors, and sparse cores are outcomes rather than reasons to select favorable runs. Distinguish acquisition validity from product-correctness failure; no efficacy conclusion is permitted if correctness fails.

Fresh copied 264-repository session each run, one selected history and one restored window. Disable update checks, auto-fetch and activation tag fetching in copied profiles; preserve the real session byte for byte. Record profile/plan/scenario/repository hashes, binary/source identities, indexed viewport, geometry, loaded count and ready/foreground witnesses. Check matched display scaling/nominal refresh, AC/battery source, low-power and thermal state. Resampling also requires Reduce Motion disabled; record an available effective witness or state the missing witness and report observed interpolation engagement separately. Do not change OS settings.

Use normal LaunchServices startup identically for both conditions, as locked before the pilots. Native recorder header supplies the measured app PID; `open -W` status is launcher status, not a native app exit code. Require completed scenario and recorder evidence. Exclude actual native scroll input and concurrent builds/game activity from acquisition, using the shared 1 Hz guard. No AX queries, UI inspections, video capture, Instruments or extra profilers during numeric runs. Other desktop activity remains a stated limitation.

Planned timeline: ready; reset to top; 12 s idle; prefill to 2000 px; 500 ms settle; two alternating warmup plans, 150 ms settle each; 1 s settle; four alternating measured plans, 150 ms settle each; 40 s final idle. Capture arms immediately at startup for 60 s. Validate actual capture covers all measured windows and idle-after, and completes before normal app exit. The installed recorder has 32768-record capacity; overflow is an acquisition failure retained explicitly. Six on plans may approach that capacity; pilots must check it.

## Input and clocks

The source is the same recorded 240 packets from `physical-capture-20261109-125646/native.jsonl` (SHA-256 in `input-plan.json`). Keep every packet, zero delta, phase, age and source timestamp. Alternate only the delta sign. Preserve `source=touch/momentum/wheel`, GPUI phase, native momentum-ended flag and captured arrival-minus-event age exactly according to the installed production mapping. No NSEvent is manufactured. This exercises the scoped GPUI route, not hardware/AppKit delivery.

The installed scenario driver uses **planned Instant minus captured event age** as each metadata timestamp. It does not reset timestamps to actual dispatch time: scheduling delay increases effective age and can cause the production >100 ms fallback. Preserve that behavior and report effective-age/dispatch-lateness distributions and counts crossing 100 ms; never reject those samples for performance.

Pair all native `scenario_scroll` records with app `scenario_input` records and traced input stages by operation. With reset, prefill, two warmups and four measured 240-packet plans, expect 1442 app/native markers, with measured packets starting at index482. Verify the actual packet sequence and all 960 measured stages. Planned CA times may be reconstructed from traced scheduled nanoseconds using the median native-CA minus traced-input `at_ms` offset. Report residuals and source ordering; do not silently use callback arrival timestamps as presentation times.

Each cycle's timing windows are anchored to its **first actual native scenario dispatch**, adding only frozen source offsets. Source-reference curves use scheduled source event times, not fitted result-dependent offsets. Keep intentional pauses out of intra-core gaps, while preserving full-source windows and tails separately.

## Frozen windows

Primary windows are momentum-only energetic cores: within each captured momentum segment, first to last source packet with |dy|>=4 px, trimmed 50 ms at the beginning and20 ms at the end. These are source-only definitions fixed before this trial's results:

- Core 1: 107211–645953 microseconds after first packet.
- Core 2: 1848719–2372904 microseconds after first packet.
- Across four measured cycles: eight cores and4.251708 s of fixed exposure.

Retain all cores, even sparse/empty. Do not shorten based on displayed motion, policy, delay or outcomes. Descriptive untrimmed momentum windows are57211–1199511 and1798719–2932084 microseconds; separately report the following fixed100 ms tail of each. Older whole-source energetic cores may be retained only as explicitly labeled legacy supplements, not substituted after seeing data.

The broader CPU/energy/submission window remains first measured phase begin+300 ms through last measured phase end−300 ms. Idle-before is ready+2500 ms through prefill-begin−800 ms. Idle-after is last measured phase end+2500 through+12500 ms. Input/display metrics and telemetry have different exposure; never divide whole-phase joules by core-only frames.

## Actual presentation and displayed-pose metrics

Cadence uses unique, positive actual drawable `presentedTime`, including repeated displayed scenes/poses. Deduplicate exact timestamp duplicates for rate/gaps, report duplicate callback counts, and mark pose ambiguous if same timestamp has conflicting known poses. Match each displayed submission to its captured prepaint history marker; logical position is `top*row_height+within`. These are logical coordinates associated with a submitted scene, not direct rasterpixel displacement.

Primary per-run cadence: total unique presentations divided by all fixed core exposure; per-core counts; median/p95/p99/max adjacent actual gaps; exceedances above2/120+.25 ms,3/120+.25 ms,4/120+.25 ms. No pair crosses a core boundary. Also report full-phase cadence and all zero/not-presented/missing callbacks/GPU errors by submission key. They are submitted-drawable outcomes, not automatically perceptible dropped frames.

Primary pose diagnostics include every known adjacent displayed pair inside each core:

- Held pair: |delta logical position|<=0.01 px (legacy <1e−6 separately if useful). Report held/known-pair counts, known/unknown pair counts and time coverage, and sum of held-pair duration divided by total known-pair duration. Unknown or ambiguous poses are not held or changed. Do not silently filter them.
- Displayed step and speed distributions include zero steps; preserve signed direction and reversal counts. Raw step variation is descriptive, because native deceleration and differing presentation gaps naturally change steps.
- Changed-pose intervals and maximum consecutive held-pose durations are supplements; they cannot replace actual cadence. Do not join across missing markers/cores or report an interpolation count as new source information.

For **uneven-step supplements**, use the same source curve in both conditions: cumulative signed source displacement, piecewise-linear between captured native source timestamps, with exact endpoints and no extrapolation. For each known displayed pair, compare observed delta with reference displacement over that pair's actual presentation times at **both fixed0 ms and12.5 ms shifts**. Report sum absolute delta residual divided by sum absolute reference travel, denominator/travel coverage and per-pair residuals. Never pick the best shift after results, and never present this as a direct raster smoothness measurement. Reporting both shifts exposes the smoothness/lag tradeoff rather than optimizing it away.

Report source-equivalent displayed-pose lag as a descriptive timing surrogate: invert the monotonic source curve for each known in-range displayed pose and subtract that source time from actual presentation time. Use the latest source endpoint time on a plateau, report ambiguous/out-of-range counts, and retain sign/direction for mirrored cycles. This is **not end-to-end physical input latency**. Prepaint-to-display marker age is separately reported and must not be mistaken for the deliberate source delay.

The resampler samples the known source curve12.5 ms behind its frame clock; it never predicts new source input. Always disclose that intentional delay. Per gesture/cycle endpoint: expected travel must match source sum within0.01 px; report first endpoint display after final nonzero actual dispatch, final displayed endpoint before next phase, missing endpoint/overshoot/reversal witnesses and displayed bounds against input received when the marker was created. Interpolation engagement (poses between discrete source cumulative endpoints) must be reported separately from correctness and efficacy. The ordinary Off path should have no such poses; On engagement does not prove human-perceived improvement.

## Resource accounting and interpretation

Use the prior independently reviewed1 Hz IOReport/IOKit/libproc method. Select contiguous raw sample indices within each phase; integrate energy/state deltas after the first selected baseline. Missing interior counters make that phase unavailable, never silently shorten its exposure. Check per-adjacent CPU/GPU counter monotonicity and state24-Mtick sum against wall time. `GPU Energy` nJ is a whole-device Energy Model estimate, not app, wall/socket, battery or total-system watts. IOKit app/WindowServer accumulatedGPUTime is accounted execution time, not peak compute utilization; shared desktop work remains confounded.

Report app CPU as percent of one core, app/WindowServer GPU ms per wall second, whole-GPU modeled W/J, state residency, observer-parent CPU and idle-before/after. Child CPU includes the measured app and must not be added as observer overhead. Wake-request counts are supplements, not CPU cost. Lower power with fewer presentations or more CPU does not establish improved efficiency at equal output.

All quantiles use linear interpolation at (N−1)*p. Aggregate run-level median/range and adjacent on-minus-off contrasts; four runs per condition are the experimental replicates. Frames are not independent runs. Do not claim statistical significance, physical-input effectiveness, stable120 Hz or reduced energy without the measured scope and tradeoffs.

Before main comparison: first On pilot failed before measured phases with Telegram still native-frontmost. Retain this setup failure. Add the same ordinary LaunchServices activation (`open -a` after scenario readiness, before the12s setup idle ends) for both conditions. Require native foreground snapshots and internal focus witnesses; retain later failures. All metric/input definitions remain unchanged, and all pilots remain excluded.
