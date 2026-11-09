# Public benchmark interpretation and privacy review

Read-only review of `publication/benchmarks/2026-11-09-metal-display-link/README.md`, `comparison.png`, `plot.py`, and a bounded text privacy scan after the independent final raw-data audit. No application, build, capture, or system changes were made.

**Verdict:** the README's numerical table, per-run outcomes, four paired directions, and chart agree with the independently recomputed data. Its leading conclusion correctly states that smoothness improvement and equal-output energy efficiency are not established. The chart is legible and its footer states the differing core/full-phase scopes and instrumentation limitation. Four serial runs per condition are not presented as independent frames or a significance test.

Two small corrections were requested from the parent before publication:

1. Change “CPU time inside submission” in the opening prose and “CPU time in submission” in the plot to **submission elapsed time** or **CPU-side submission duration**. These probe durations include blocked drawable acquisition. They do not measure CPU execution time, and total measured app CPU increases. Keep the acquisition scope explicit.
2. The protocol's opening workload description still contains the private selected-repository name. Replace it with the same neutral placeholder used in window witnesses. The scan found no real absolute user paths, email addresses, or private selected HEAD across 84 exported text files. Opaque session/profile hashes remain as equality evidence, with the private files themselves omitted.

A helpful additional sentence is that zero/not-presented callbacks describe submitted drawables without a positive actual display timestamp; they are not automatically counts of perceptible dropped animation frames. The README already keeps these outcomes separate from actual cadence and does not label them as visible hitches.

No further numerical or interpretation blocker was found. Any regenerated chart/export should refresh checksums. `final-data-review.json` and the auditor source were initially private review artifacts; use the export redaction pass rather than copying private files blindly.

## Final verification

The parent corrected the submission wording and rerendered the chart, added the explicit submitted-drawable versus perceptible-drop caveat, and removed the remaining private workload name. I inspected the updated chart and repeated the bounded scan across 86 exported text files: no real absolute user paths, private workload name, or private selected HEAD remains. **Both requested corrections are resolved; no remaining publication blocker was found.** The final chart SHA-256 is `de80c24dc2a3c0d040237420c9b482b04d1ee18e064b950628a89ea071cce511`.
