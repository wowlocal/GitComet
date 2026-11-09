# Pilot acquisition and arithmetic review

**No blocker to the balanced main series.** Two successful pilots are retained separately and excluded from the eight-run comparison. The failed initial On pilot is also retained; it stopped before benchmark phases with the wrong native-frontmost application. The parent disclosed the matched main-series normal activation after readiness, before the12 s setup idle ends. Input/metric definitions remain unchanged.

I independently recomputed both successful pilots' unique actual presentation counts, p95/p99 gaps, held logical pair counts and duration-weighted held time, rather than relying only on the saved analyzer report. I also independently recomputed all six contiguous phase integrals (CPU, app/WindowServer GPU counters, whole-GPU modeled energy, state residency) and checked cross-pilot binary/profile/scenario hashes and both ready/after-scroll environment snapshots. All matched.

- Each successful pilot has1442 paired native/app input markers and960 measured stages, no native hardware scroll events, zero recorder drops/overflow, and complete primary/idle-after capture coverage.
- Maximum native-versus-traced-input clock residual is0.0074 ms Off and0.0107 ms On. No effective measured source age exceeded100 ms.
- All six cycle endpoints pass within0.01 px, and no marker direction or received-path bounds violation occurs. Core pose coverage is complete, without unknown or ambiguous poses.
- Off has no between-source-endpoint core poses; On has493. This demonstrates engagement only, not a physical-input/user-feel result.
- Record counts are20775 Off and29187 On against32768 capacity. Keep overflow checks in every main attempt.
- The parent observer used1.262% and1.272% of one core. These are parent-process lifetime measurements; child CPU includes the app.

Off pilot idle-after is desktop/compositor-confounded: whole-GPU model about0.508 W and WindowServer296 ms/s, versus0.124 W and105 ms/s in the On pilot. These are retained observations, not pure app power. Do not subtract them to manufacture an app-watt result. Other pilot performance numbers remain excluded from the final comparison.

Detailed independent checks and the failed-attempt identity are in `pilot-review.json`. The analyzer outputs are separate `analysis-pilot-*.json` files, preserving original acquisition artifacts.
