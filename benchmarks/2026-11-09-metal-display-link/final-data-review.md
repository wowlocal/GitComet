# Independent final data review

**Verdict:** recorded controls and raw arithmetic pass. This workload does not demonstrate smoother displayed cadence or better energy efficiency at equal output for PR47. No remaining numerical or control blocker was found in these eight valid runs.

I independently recomputed the results from saved `frames.jsonl`, `native.jsonl`, and `measurement.json`; the review script never launches an app or touches UI. It reproduces every reported condition metric and all adjacent fixed-minus-stock contrasts. The complete computed evidence is in `final-data-review.json`, and the repeatable auditor is `acquisition-reference/independent-final-audit.py` (a reference copy whose full provenance checks require the private local originals).

The valid run order is ABBA BAAB, four runs per condition. All pilots are excluded. The failed first ordinal-3 fixed attempt is preserved beside its valid retry. A separate fixed pilot also failed with the same native-focus timeout, before any benchmark phase in either case. There is no demonstrated PR attribution for those two setup failures; the timing claim is conditional on successful foreground/readiness controls.

## Suggested public table

Cells are **median [minimum–maximum] across four runs**, except the explicitly separate worst-gap statement. Gap percentiles are computed per run from unique positive actual drawable `presentedTime` values inside the eight source-defined motion cores, without pairing across pauses. These cores provide 4.601196 seconds of fixed exposure per run. CPU, energy, submit timing, and submission outcomes use the broader predeclared scrolling phase, so their exposure differs.

| Metric | Instrumented stock | Instrumented PR47 |
| --- | ---: | ---: |
| Unique positive actual presentations/s, fixed motion cores | 104.76 [103.23–109.54] | 98.67 [89.76–103.89] |
| Per-run p95 presentation gap, ms | 16.667 [16.667–16.667] | 16.667 [16.667–16.667] |
| Per-run p99 presentation gap, ms | 16.667 [16.667–16.667] | 16.667 [16.667–16.667] |
| Full submit including drawable acquisition, per-run median ms | 5.415 [5.304–5.449] | 0.316 [0.312–0.321] |
| App CPU, % of one core | 22.83 [20.12–23.69] | 28.74 [26.36–29.30] |
| App IOKit GPU accounted time, ms/wall s | 74.92 [72.42–79.44] | 45.77 [45.49–51.62] |
| Whole-GPU Energy Model, W | 1.428 [1.388–1.439] | 1.190 [1.123–1.241] |
| Zero/not-presented submitted drawables per full phase | 0.0 [0.0–0.0] | 204.5 [190.0–358.0] |
| Observer parent CPU, % of one core | 1.281 [1.251–1.290] | 1.293 [1.263–1.307] |

The **worst observed core presentation gap** was **16.671 ms stock versus 20.833 ms PR47**. Across all four runs, gaps above 16.917 ms numbered **0 versus 1**; neither condition exceeded 25.250 or 33.583 ms. Both conditions had per-run median gap 8.333 ms and p95/p99 about 16.667 ms. Core presentation rate was lower with PR47 in three of four adjacent comparisons. There were 1,943 stock versus 1,799 PR47 unique core presentations over equal summed exposure; this is descriptive, not a significance test.

Full-phase submission accounting retained every outcome: stock had 0 zero/not-presented callbacks among 5,070 submissions; PR47 had 957 among 5,646. No missing presented/GPU callbacks or GPU errors were observed in either condition. A zero/not-presented callback describes a submitted drawable that was not positively reported displayed; it is not by itself proof of a visible animation hitch.

The PR substantially reduces blocking in the full submit path (including drawable acquisition), and input-dispatch p95 falls from a median 12.509 to 6.118 ms. It nevertheless increases measured app CPU by 5.57–6.25 percentage points of one core in every adjacent pair. Lower submit blocking must not be equated with smoother actual presentation.

## Energy and idle interpretation

The whole-GPU Energy Model average was lower in every adjacent PR47 pair, as was app IOKit GPU accounted execution time. The public report must **not** call this improved energy efficiency: output differs, app CPU increases, and the energy counter is shared device GPU energy. The result does not quantify battery impact or total system power, and it does not provide per-app watts. Do not divide full-phase energy by core-only frame counts because the windows differ.

Whole-GPU energy comes from IOReport `GPU Energy` in nJ, integrated only across contiguous included sample intervals and divided by their endpoint wall duration. Performance-state residency uses `GPUPH` 24-Mtick units. All 24 phase integrals reproduced, all CPU/app/WindowServer GPU counters were monotonic and present, and state-tick totals matched wall duration within 0.011%. Scrolling telemetry retained 11–12 sample points spanning 10.041–11.043 seconds per run; it is not high-resolution instantaneous power.

Idle-after app GPU time was 0 in all stock runs and 0–0.170 ms/s in PR47 runs. Idle-after app CPU was 1.047–1.075% stock and 0.632–1.224% PR47, with instrumentation and background services still enabled. Shared WindowServer GPU accounted time remained 95.93–100.63 ms/s, while whole-GPU modeled idle-after power ranged 0.059–0.113 W. These are quiet device observations, not pure per-app power. Scrolling WindowServer time was 444.46–477.99 ms/s stock and 455.37–535.81 ms/s PR47; do not attribute all of it to GitComet or add it as an independent GPU utilization percentage.

Observer parent CPU was 1.251–1.307% of one core over the process lifetime. Its child CPU counter includes the measured app and launcher; it is not additional observer overhead. Both conditions use the same observer implementation and 1 Hz telemetry. The installed app’s ordinary uninstrumented workload may differ.

## Control and provenance audit

- All eight valid runs have exactly 1,442 app scenario inputs, 1,440 paired native scenario-scroll records, and 960 measured input stages. Packet signs/order match the frozen 240-packet plan, including alternating directions. Each has 12 before/after position witnesses at 2,000/5,468 px and 16 active/ready single-window witnesses.
- All runtime sessions report 264 repositories with one loaded. Fresh copied input-profile hash, scenario hash, input-plan hash, selected-repository identity, real-session invariance, and captured history viewport match. This tests the same repository window rather than all 264 repositories rendering simultaneously.
- Ready and after-scroll snapshots match the built-in 120 Hz, 2× display, fixed window/viewport bounds, AC power, low-power mode off, thermal state nominal, and target foreground PID. The runner checked each second for the named game and compiler processes. Other background GPU consumers cannot be completely excluded.
- Both conditions match app commit `ad5df1d185c1a8805870bffcfde592d5e3ce355a` with identical app/observer source hashes, build command, Rust toolchain, features, release optimization/fat-LTO/codegen settings, and binary hashes matching their build manifests. Stock framework is `c55d73659dd6560d3e70281056f841e6d366c0e5`; PR47 is `aad11809345380e3ae2d79f6cfcfc5aaf2af4edc`. The separate `instrumentation-review.md` and `instrumentation-parity.json` establish reconstruction of the 24 stock/fixed production files and byte-identical observers.
- Every capture completed at 50 seconds with zero recorder drops/marker overflow. All primary cores and idle-after windows finish before the capture deadline. Native/App clock residual maximum across valid runs is 0.1603 ms. Unique timestamps are deduplicated; no fixed-core exposure was discarded.
- The stock/fixed table is confined to the eight valid balanced runs; the two successful pilots and two failed attempts are not additional performance replicates. Four runs per condition on one machine do not establish population-level significance.

The report should describe an **instrumented, same-input synthetic replay comparison**. It is useful evidence for a PR discussion, but it does not reproduce every physical trackpad momentum path, isolate every background compositor consumer, establish GPU saturation, or prove an energy-efficiency improvement at equal visual output.
