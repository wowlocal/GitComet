# Momentum analyzer: independent source review

Source reviewed: `target/app-scroll-validation/energy-review/analyze.py` and
the frozen protocol/input definitions. This reviewer did not execute an app,
build, profiler, analyzer, or synthetic test during this pass and did not read
the unfinished main measurements. The energy agent's saved synthetic results
were inspected as artifacts.

## Resolved finding

The original analyzer (`17c0ef54f14433f93f155cf5dcd4a91e3f958da3c30819e926dd4d74db09a45a`)
filtered out unknown poses before choosing a cycle's last display. A known
endpoint followed by an unknown or ambiguous actual display could incorrectly
pass final-endpoint correctness.

The corrected source (`fd1113e088139e0ab41855f40e875e69723fd4666b6e0e47d9db0958ec470ca3`)
selects the last actual positive display first, retains explicit known,
unknown, ambiguous, or no-actual status, leaves an unknown assessment null,
and requires `is True` for aggregate endpoint success. Earlier known arrival
and last-known pose are separate supplements. Saved cases cover known→unknown,
known→ambiguous, unknown→known, wrong endpoint, empty display, and conflicting
same-timestamp poses. The correction addresses the finding without changing
input, acquisition, thresholds, or fixed metric windows.

## Other checks

- Cadence uses positive actual presentedTime and deduplicates exact
  `(window,timestamp)` pairs, not nearby display ticks. Duplicate callback
  counts remain visible. Conflicting known poses or a missing marker leave
  pose unknown while preserving the actual cadence sample.
- Held/change/speed calculations use adjacent known pairs only. Unknown
  intervals are counted and never bridged into a held/change interval. Core
  windows remain separate and retain fixed exposure even when sparse.
- Scheduled source time is reconstructed from traced scheduled nanoseconds
  using a measured CA/trace offset, then subtracts the preserved source age.
  Actual dispatch lateness is measured separately. It is not silently
  substituted into the reference source curve.
- Mirrored cycles preserve signed cumulative displacement. Inverse timing
  uses a monotonic per-gesture curve, with latest-time plateau inversion, so
  a later touch cannot steal the endpoint time of an earlier momentum glide.
  Out-of-range/unknown inverse results are counted.
- Both fixed0ms and12.5ms reference shifts are retained. Their residuals use
  known adjacent-pair coverage and explicit travel denominators; no best shift
  is selected from outcomes. Interpolation engagement is labeled separately
  from correctness or efficacy.
- Primary momentum cores, full momentum, fixed tails, and broad resource
  phase scopes remain distinct. Whole-phase energy is not divided by
  core-only output. Contiguous telemetry indices, reset counters, complete
  capture/overflow status, native-input rejection, policy equality, and
  run-level adjacent contrasts are checked or reported.

No remaining concrete analysis correctness finding in the corrected source.
One interpretation limit: when duplicate callbacks agree on pose but refer
to different marker times, the implementation selects the newest marker for
age. That is the youngest associated marker age, not proof of which duplicate
drawable furnished the onscreen pixels. Disclose this if actual duplicates
occur; it does not affect the unknown-pose correction or unique cadence count.
