# Isolated GitComet PR #749: saved presentation and CPU observations

This packet contains normal and forced completed experiments. Each experiment has 16 fresh-process runs, eight per build, in the frozen ABBA BAAB ABBA BAAB order. The experimental replicate is a run; presentation intervals are not independent replicates. Normal and forced GPUI accessibility-core results remain separate.

Before is GitComet `14b3cba1a8fcd51ae6a32e8bbc385556625bf5b2`; after is PR #749 at `7b0229c82a09383a3cada51834dde4decc9aa7b4`. Both use public GPUI `c55d73659dd6560d3e70281056f841e6d366c0e5`, the same observer/replay overlays, the same release settings and 264 open repositories. No elasticity, row-geometry, momentum-resampling or framework PR #47 changes are included. Build paths differ, which can affect binary layout. Source, patch and packaged-binary hashes are in `sources/identity.json` and `sources/builds.json`.

The workload is generated GPUI pixel-wheel replay, using the unchanged packet plan in `stock-vs-fix/input-plan.json`. It is not physical trackpad input. The normal arm requires passive accessibility flags to remain false and the completed-tree counter to remain zero, including the final witness. The forced arm requests GPUI's existing accessibility path once before warmup and checks its activity/counter advancement. Forced GPUI accessibility is a positive control, not a native external accessibility client or VoiceOver test.

Each arm's `analysis.json`, paired-point graphs and per-run interval ECDF describe actual positive drawable-presentation timestamps and root-process CPU counters. The eight adjacent after-minus-before run pairs supply the exploratory, endpoint-specific uncertainty intervals. Undefined CPU outcomes remain unavailable. Do not infer energy use, physical scrolling feel, equal raster output, all-project rankings or general device performance from this packet. A nonsignificant comparison does not establish equality. See the historical, pre-capture `method/PREREGISTRATION.md` for the endpoint definitions and directional gate.

The common app/native recording and 1 Hz observer can affect the workload. The observer's own CPU field covers only its Python PID; it excludes helper children and app/native recorder work. There is no fully uninstrumented replay control in this packet. Sampled CPU pilots and native-recorder-off overhead runs are outside the 16-run presentation experiments and are not included in their statistics. No energy counters are analyzed or exported here.

## Reproduce the saved-data analysis

Use Python 3 with SciPy and Matplotlib available. The exporting environment versions are recorded in `export-manifest.json`; no dependency installation or native access is performed by these commands.

```sh
python3 reproduce.py
python3 reproduce.py --output /path/to/new-reproduction-directory
```

The first command verifies the complete file inventory and recomputes all published run outcomes and paired summaries using the byte-identical frozen analyzer. The second also writes new graphs and analysis into a new directory outside this packet. It never overwrites published evidence. The portable wrapper supplies dataset-relative paths because the original analyzer's acquisition CLI used local absolute paths. It does not modify the analyzer. Floating-point comparisons permit only a `1e-12` relative/absolute tolerance for library-version rounding; export-time parity against the original local analysis was exact.

## Privacy and provenance

This is a selected, sanitized export, not a copy of a user profile. Native timing JSONL is byte-identical after a strict numeric/enum schema check. Retained application frame records preserve their clocks and numeric fields; repository witnesses use `<large-repo>` and selected-commit fields are omitted. Unneeded frame events, repository/profile lists, window titles, commit messages, stderr, local paths, screenshots, sampled stacks and legacy energy-named counters are omitted. Environment records retain numeric control witnesses but replace the descriptive power-source string with `AC`. CPU counters and native presentation times used by the analyzer are unchanged.

Local source-file hashes are retained under public run labels in `raw-source-sha256.json`. Public hashes describe the sanitized bytes, so redacted frame and measurement hashes intentionally differ from local source hashes. Paths and measurement hashes in the public analysis are rebased to the exported files; analysis numbers are unchanged. Failed attempts remain in each manifest as descriptive metadata. Fixed control-failure messages are retained; any other private error text is represented by its SHA-256 and an explicit withheld marker. Such attempts are never pooled into the 16 valid runs. `export-validation.json` records the exact numeric/structure parity check against completed local evidence.

Prepared with OpenAI Codex at the reporter's explicit request. This packet reports a bounded observation, not a maintainer endorsement or an assurance of subjective smoothness.
