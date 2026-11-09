# Independent saved-data review

All eight fresh-process main attempts passed the registered balanced order and acquisition/control gates. No main attempt was excluded. Each run retained 160 generated CUA requests; the largest subcall lateness was 137ms and duration 135ms, below the 200ms lateness guard. Raw sample counts/sequence, source identities, clock mappings, 40-repository/session witnesses and native before/after controls passed.

Independent arithmetic recomputed cumulative CPU/GPU rates, contiguous phase exposure, whole-GPU nJ sums and 24Mticks residency, medians/ranges and all four adjacent contrasts. No discrepancy was found. The documented portable reanalysis command also matched all 2,734 non-path scalar fields in the exported analysis.

| Scrolling envelope | GitComet | Fork |
|---|---:|---:|
| Main-process CPU, median % of one core |10.92|12.89|
| App GPU execution, median ms per wall second |8.413|Unavailable|
| Observer CPU, median % of one core |1.57|1.51|
| Shared whole-GPU Energy Model, median W |0.404|0.953|

Fork-minus-GitComet main-process CPU was positive in all four pairs: 2.27, 1.62, 2.00 and 1.97 percentage points of one core. This applies to the generated workload and approximately matched history viewport; exact pixels, row ordering, frame cadence and physical trackpad output were not matched.

Fork had one matching GPU client with empty AppUsage in all 215 raw samples. Its process GPU counter is unavailable, not measured zero. GitComet had one readable client in all 218 samples. WindowServer attribution and optional CUA-process CPU were unavailable under this unprivileged collection. Observer CPU is separate and not added to app CPU; helper-inclusive or total-system CPU is not computed.

Shared-GPU power cannot be attributed to the app. The no-app desktop baselines were 0.901W before and 0.970W after—both above GitComet scrolling. Still-phase medians were approximately 0.21W with GitComet versus 0.81–0.83W with Fork. Different window coverage/static layouts and background/compositor activity are material confounds. Subtracting these baselines would not isolate app watts. These data establish neither total-energy superiority nor a renderer architecture explanation.

Both descriptive desktop captures independently passed raw count/exposure/energy arithmetic. Each contains 21 samples and approximately 20.0 seconds of integrated exposure. CPU-energy counters were retained but not validated/analyzed; battery, socket and total-system energy were not measured.

Before/after process/environment witnesses do not prove continuous background silence or CUA internal AX state. GPU client identities/lifetimes were not recorded, so a monotone aggregate recomposition can escape reset detection. Sequential query spans quantify timing skew. The active input was 40 common repositories, not the user's full 264-repository session. Private profile/repository identities are represented by preservation booleans and remain omitted from the public package.
