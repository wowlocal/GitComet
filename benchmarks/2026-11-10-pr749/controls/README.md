# Recorder-off CPU control for PR #749

All eight planned runs passed the independent saved-file audit, with no invalid attempts or replacements. The order was ABBA BAAB (A=before, B=after), giving four adjacent run pairs. The native timing recorder was disabled; the common app probe and 1 Hz process sampler remained enabled. This control has no actual-presentation denominator.

The CSV contains only allowlisted numeric controls and public condition/ordinal labels. It omits local paths, repository names, profiles, PIDs, wall-clock timestamps, environment guard files and application logs. `process_cpu_delta_ms` is the difference between the two observed process CPU counters; `counter_exposure_s` is the duration between their recorded read-bracket midpoints. `percent_one_core = process_cpu_delta_ms / counter_exposure_s / 10`. The first/last query bracket widths are retained in milliseconds. No CPU interpolation is used.

| Outcome | Value |
|---|---:|
| Before mean one-core CPU | 27.23842466% |
| After mean one-core CPU | 24.10018951% |
| Mean paired after−before | -3.13823515 percentage points |
| Paired 95% Student t CI (4 pairs, df 3) | [-8.25851358, 1.98204327] percentage points |
| Within-build MAD, before/after | 0.97007299 / 0.34528302 percentage points |
| Directional endpoint gate | Not met |

The control did not detect a CPU-over-observed-time difference under its predeclared four-pair rule. Recorder-on and recorder-off arms occurred in separate time epochs rather than randomized observer allocation. Do not pool them, replace the primary native-on analysis, or causally attribute their entire difference to observer overhead. This is not a frame cadence, energy, physical trackpad, verified equivalent-output, or renderer-isolation result.

The source pair is before `14b3cba1a8fcd51ae6a32e8bbc385556625bf5b2` and after `7b0229c82a09383a3cada51834dde4decc9aa7b4`, with common app observation code. The independent audit source is `aa979ee7628228e6c5641b050ca3959aa6207386270bad130082e3803050242f`; its private raw-data review report is bound by SHA256 `815e6f27beba24abc086291bbaab1ba6b5c7439274f7d8b7482060cddbe7acde`. The CSV SHA256 is `6dc22b535bb2ae22f9317356da8cc0e58a972ba33a85236ef11b25e7ede52ce2`. Raw guard files remain private.

Prepared and checked with OpenAI Codex assistance. This disclosure does not claim human review of the result.

To reproduce the control interval from `recorder-off-cpu.csv`, pair adjacent rows, subtract before from after in each pair, then compute `mean ± 3.182446305284263 × sample_stdev / sqrt(4)` (two-sided 95% Student t interval, 3 degrees of freedom). The four differences are +0.22828830, −7.51731615, −2.77467254 and −2.48924023 percentage points.
