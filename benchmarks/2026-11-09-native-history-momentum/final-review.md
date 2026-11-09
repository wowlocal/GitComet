# Independent final same-binary review

**The arithmetic and recorded controls pass. The supported result is narrower than a general smoothness improvement:** momentum resampling removes sparse repeated logical poses in these sustained-motion cores, with higher CPU and a source-delay tradeoff. Actual frame cadence does not improve. This is synthetic captured-metadata replay on one Mac, not a physical trackpad/user-feel result or direct raster-motion measurement.

Eight valid ABBA BAAB runs, four per mode, use the same installed `fe34d0636fe35af0ccbc693ce2b0861499a003c9` instrumented release binary (`f3172102…9455c3`). There are no failed main attempts. All pilots, including the failed first On startup, remain excluded. Each run includes eight fixed momentum-only cores totaling4.251708 s. Table cells below are median [minimum–maximum] of four run-level measurements; CPU/energy use the broader full scrolling phase.

| Metric | Off | On |
| --- | ---: | ---: |
| Actual unique core presentations/s | 117.95 [115.25–118.78] | 116.19 [114.78–118.78] |
| Per-run p95 actual gap, ms | 8.3334 [8.3334–8.3335] | 8.3335 [8.3335–8.3335] |
| Per-run p99 actual gap, ms | 16.667 [8.750–16.667] | 16.667 [8.334–16.667] |
| Source-equivalent displayed-pose lag, per-run median ms | 51.137 [47.795–51.402] | 54.100 [54.098–54.101] |
| App CPU, % of one core | 29.15 [29.06–29.25] | 30.55 [30.43–30.87] |
| App GPU accounted execution, ms/wall s | 56.29 [54.75–58.09] | 53.87 [52.69–56.09] |
| Whole-device GPU Energy Model, W | 1.248 [1.177–1.288] | 0.976 [0.886–1.084] |

Off has **18 held logical pairs out of1966** across four runs; On has **0/1949**. The per-run held-pair fraction is0.20–2.07% Off, median0.71%, and0% On. Duration-weighted held fractions are0.20–1.99% Off and0% On. Every observed held run is about one8.333 ms presentation interval. All core poses and adjacent pairs are known, without duplicate actual timestamps, ambiguous markers or source-inverse omissions. These are logical prepaint coordinates, so the result must not be described as proof of zero repeated raster frames.

Actual cadence is lower in two On pairs and equal in two. Both modes have p95 gap about8.333 ms and worst observed core gap about16.67 ms; no core gap exceeds the predefined16.917/25.250/33.583 ms cutoffs. Per-run p99 is variable because occasional two-period gaps remain. Do not claim stable120 Hz, eliminated frame drops, or a higher refresh rate.

## Per-run and paired findings

| Ordinal | Mode | Core Hz | Held/known pairs | Source lag median, ms | App CPU, % core | GPU model W |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | off | 118.54 | 1/496 | 47.795 | 29.17 | 1.177 |
| 2 | on | 115.01 | 0/481 | 54.100 | 30.87 | 0.975 |
| 3 | on | 114.78 | 0/480 | 54.100 | 30.43 | 0.886 |
| 4 | off | 115.25 | 10/482 | 51.387 | 29.25 | 1.249 |
| 5 | on | 117.36 | 0/491 | 54.101 | 30.44 | 0.977 |
| 6 | off | 117.36 | 3/491 | 51.402 | 29.06 | 1.247 |
| 7 | off | 118.78 | 4/497 | 50.888 | 29.12 | 1.288 |
| 8 | on | 118.78 | 0/497 | 54.098 | 30.66 | 1.084 |

Contrasts are On minus Off, using the predeclared adjacent pairs.

| Off/On ordinals | Δ core Hz | Δ app CPU, points | Δ source lag median, ms | Δ shared GPU model W |
| --- | ---: | ---: | ---: | ---: |
| 1/2 | -3.53 | +1.69 | +6.304 | -0.201 |
| 4/3 | -0.47 | +1.18 | +2.713 | -0.363 |
| 6/5 | +0.00 | +1.37 | +2.699 | -0.270 |
| 7/8 | +0.00 | +1.53 | +3.211 | -0.205 |

The source-normalized delta-error supplement is mixed: On improves in three of four pairs against the0 ms source reference and two of four against the12.5 ms reference. Neither reference supports a universal uneven-step improvement. Both fixed shifts remain reported; no fitted lag or favorable reference was selected after results.

## Latency and resource interpretation

The controller deliberately samples the known source curve **12.5 ms behind its frame clock**. The observed source-equivalent displayed-pose lag is about51.14 ms Off versus54.10 ms On; paired increases range2.70–6.30 ms. These numbers are compound modeled surrogates involving source-event timing, dispatch/display phase and presentation age. They do not mean that the algorithm adds only3 ms, that hardware input latency was measured, or that the12.5 ms lookback disappeared. Prepaint-to-display age remains a separate roughly40.8 ms observation and is not the algorithmic source delay.

App CPU rises in every pair, by1.18–1.69 percentage points of one core (about29.15→30.55% in the run medians). App GPU execution-time contrasts are mixed; its lower median must not be called a uniform per-run saving. Whole-device modeled GPU power is lower in every On pair, but WindowServer accounted GPU time also differs substantially: Off566–591 ms/s, On428–440 ms/s. Full-phase submissions differ (Off1412–1413, On1017), including source pauses/tails/cached scenes outside the primary cores. These are useful workload observations, not isolated app watts or equal-output/total-system energy efficiency. Raw CPU energy counters were recorded but were not validated or analyzed; battery discharge, socket power and total-system energy were not measured.

Idle-after app GPU time is0 in every main run. App CPU is0.707–0.747% Off and0.692–0.714% On with diagnostics enabled. Whole-GPU idle-after model ranges0.107–0.141 W and shared WindowServer98–106 ms/s; before-idle model ranges0.115–0.150 W. No background/observer energy is subtracted. The parent observer consumes1.252–1.322% of one core over process lifetimes; child CPU includes the app. The earlier confounded Off pilot idle-after remains a separate excluded pilot observation.

## Independent evidence checks

Unique actual display counts, p95/p99, held-pose duration fractions, both source-curve residuals and source-curve inversion were independently recomputed from raw records. All24 contiguous1 Hz CPU/GPU/energy/state-residency phase integrals and all adjacent contrasts reproduce. Each run has1442 paired app/native markers,960 measured stages, correct source metadata/signs,16 active/ready witnesses and the same264-repository copied profile with one repository loaded. Binary/scenario/profile hashes, indexed viewport, both ready/after environment snapshots, nominal120 Hz/2× display, AC power, Reduce Motion off and nominal thermal state match. Other desktop GPU consumers cannot be entirely excluded.

All48 cycle endpoint assessments use the final actual positive display, with no unknown/ambiguous final poses. A supplementary check of all96 original gesture endpoints (64 measured,32 warmup) also passes within0.01 px; maximum absolute error is0.000019685 px. No received-path bound or monotonic-direction violation occurs. Recorded source-equivalent clocks have maximum residual0.0105 ms; all measured effective source ages stay below27.814 ms, so the100 ms stale-source guard is not crossed. Capture records peak at29198/32768 with zero drops/overflow, and every core/idle-after window lies before the60 s capture deadline.

The final-display endpoint handling correction was made during acquisition as a documented analysis correctness fix, without reading main results or changing inputs/windows/thresholds. The prior analyzer and seven synthetic cases are preserved. No acquisition failure was silently dropped. Four serial runs per mode are experimental replicates; frames are not independent trials and no statistical significance is claimed.

The complete arithmetic evidence and independently repeatable raw reviewer are `final-review.json` and `final-review.py`. The main analyzer preserves raw windows, outcomes and coverage in `analysis.json`.
