# Method and interpretation

The unchanged pre-pilot [protocol](analysis/PROTOCOL.md),
[lock](analysis/prepilot-lock.json) and [input plan](analysis/input-plan.json)
define the analysis before acquisition. References in that original protocol
to local artifact folders identify the recorded source manifest now published
as [source/source-manifest.json](source/source-manifest.json). The original
private manifest hash is retained; its absolute paths are not.

The app source is GitComet `ad5df1d185c1a8805870bffcfde592d5e3ce355a`,
with the common absolute-time replay observer and a rendered-history logical
marker. The framework is gpui-ce `c55d73659dd6560d3e70281056f841e6d366c0e5`,
plus production PR #47 at `aad11809345380e3ae2d79f6cfcfc5aaf2af4edc`, the
common numeric observer and a mechanism-observation delta. Full overlays and
their baseline/delta decomposition are available in `source/`.

This app does not include the separate elastic-scroll or momentum-resampling
experiments. Its scenario dispatches bare pixel/Moved GPUI events. A 240-packet
plan, derived from an earlier capture's timing/deltas, lasts 2.932084 seconds
and sums to -3,468 px. Reset, prefill, two warmups and four measured alternating
plans produce 1,442 app inputs, of which 1,440 have scenario native-clock
markers. Programmatic dispatch is explicitly distinguished from AppKit input;
neither capture contains native-input records.

Acquisition used a fresh copied 264-repository profile with one loaded history.
The profile and repository contents/identities are private and omitted. The
published records retain readiness, loaded/total counts, geometry and 12
before/after endpoint witnesses. The selected indexed history had 811 rows and
an observed 1,095 × 882-point viewport. The window bounds were
1,714 × 1,037 points on a built-in 120-Hz, scale-2 display, on an Apple M5 Max
running macOS 27.2. Low Power Mode and Reduce Motion were off; thermal state
was nominal and power source AC at both environment checks. These are
before/after checks, not continuous power/thermal/focus guarantees.

No game, build, stack-sampling profiler, video or AX/UI inspection was used during the
finite numeric acquisition. The app was launched through LaunchServices into a
distinct probe bundle, and it did not replace the installed app. Both complete
attempts are retained: a pilot excluded from confirmation and one confirmation.
There were no subsequent probe retries used in this dataset.

The bounded recorder arms once at the first scenario scroll and runs for
60 seconds. It retains numeric records in bounded memory and flushes in a
background writer. Completeness requires its final duration footer, ordered
contiguous sequence numbers, zero recorder drops and zero marker overflow.
These checks do not imply that every drawable was displayed. Instrumentation
can itself perturb timing; no matched observer-cost control was run.

## Clocks and selection

Native `at_s` uses `CACurrentMediaTime()` at record creation. Metal update
recording follows retain/getter reads and precedes the existing GPUI callback;
it is not an exact delegate-entry timestamp. GPU host timestamps and positive
actual presentation timestamps use the native host-time domain. App Unix
timestamps are mapped using paired scenario markers; mapping residuals are
reported, not assumed zero. Callback record order does not establish GPU order.

`deadline_s` is the assigned CPU deadline for calling the drawable presentation
method. `target_presentation_s` is a distinct estimated display target. GPU
rendering can finish after the CPU deadline. `submit_end` follows the rendering,
presentation-registration and commit path's return; it does not timestamp the
deferred presentation method itself. The probe records no exact enqueue,
commit, scheduled-handler or `drawable.present()` call timestamp.

The full-capture summary is descriptive and includes idle. The registered
scrolling interval runs from replay-0 begin +300 ms to replay-3 end -300 ms.
Eight source-active intervals are independently defined by the plan, totaling
4.601196 seconds. Gaps are never bridged across those separate intervals.

Updates are selected by recorded callback time; submission outcomes by submit
begin; exact target groups by their assigned target timestamp; actual displays
by positive `presentedTime`. Whole-capture joins retain callbacks outside a
selection boundary. Exact serialized target timestamps are grouped without a
post-hoc tolerance. Quantiles interpolate at `(N-1)*p`.

`new_scene` compares the preceding **submission**. Actual scene changes and
held logical poses compare adjacent unique positive displays within each
window, preserving unknown poses. The logical marker snapshots the geometry
used to render history, before measurement can prepare the next model state.
It is not a screenshot or proof of raster content. This stationary-history
protocol avoids the marker's last-known-state limitation after navigation.

Observer measurement files are included for completeness, without an energy
conclusion. CPU counters are process scopes, child counters are separate, and
GPU process counters can be absent or reset. Device/SoC fields describe shared
system activity or modeled counters, not energy attributable solely to this
app. The older observer's missing/invalid per-client GPU aggregation is not a
guarantee of observed zero; these measurements are not used in the findings.

## Publication transformations

Native traces, scenarios, registered analysis source/plan/protocol and six
source overlays are byte-identical copies. App JSONL is byte-identical except
for 16 repository strings per capture. Measurements preserve every numeric
leaf and replace only the environment battery-description string with `AC`.
The source/build records replace home paths and personal signing data with
portable labels. Private session/repository identities and hashes are omitted.
Generated analyzer tables equal the original tables except for the public
relative capture path. The raw audit changes only paths, run labels and output
selection. Original and exported hashes and equivalence checks are in
`export-provenance.json`.
