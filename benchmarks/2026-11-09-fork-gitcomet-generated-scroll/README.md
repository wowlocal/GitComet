# GitComet and Fork: generated scrolling resource comparison

The generated wheel-burst workload recorded less main-process CPU in GitComet. The shared GPU-power readings are confounded: the desktop with neither app open consumed more modeled GPU power than GitComet scrolling. These measurements do not establish which app uses less total energy.

Four fresh processes per app were acquired on one Mac in the registered balanced order. All pilots are excluded. Exact visible output, native trackpad motion and actual presentation cadence were not matched.

Both apps used the same 40-repository input and active large history. GitComet is the installed combined private release (source fe34d063, private GPUI4b3); Fork is 2.71.1. Exact executable and observer hashes are in `input-plan.json` and raw headers. This is not the separate current GPUI PR47 comparison.

Each 45-second workload has 10 seconds still, a 20-second scrolling envelope (including 2 seconds quiet padding at each end), then 15 seconds still. Sixteen groups request ten 0.1-page moves at planned 50ms spacing, down/down/up/up repeated. Command timings are retained. These requests are not native120Hz packets or physical trackpad momentum.

History widths were approximately 1095 points; GitComet history height 884 versus Fork 914. Row heights, exact history ordering and static layouts differ. The common fresh-process screenshot and warmup occurred before numeric recording. No explicit AX inspection occurred during numeric phases; CUA internal AX use is unverified. Endpoint environment/interference witnesses do not prove continuous background silence.

| Scrolling-envelope metric | GitComet median [min–max] | Fork median [min–max] |
|---|---:|---:|
| App CPU (% of one core) | 10.92 [10.62–11.23] (n=4) | 12.89 [12.84–12.91] (n=4) |
| App GPU execution (ms per wall second) | 8.413 [8.127–9.427] (n=4) | unavailable [unavailable–unavailable] (n=0) |
| Whole-GPU Energy Model (W) | 0.404 [0.403–0.415] (n=4) | 0.953 [0.922–0.970] (n=4) |
| Observer CPU (% of one core) | 1.57 [1.53–1.67] (n=4) | 1.51 [1.49–1.54] (n=4) |
| WindowServer GPU execution (ms per wall second) | unavailable [unavailable–unavailable] (n=0) | unavailable [unavailable–unavailable] (n=0) |

| Still-phase whole-GPU model | GitComet W | Fork W |
|---|---:|---:|
| idle-before (four-run median) | 0.215 | 0.811 |
| idle-after (four-run median) | 0.207 | 0.830 |

| Desktop with neither app open | Whole-GPU model W | Observer CPU (% of one core) |
|---|---:|---:|
| before (one descriptive capture) | 0.901 | 1.53 |
| after (one descriptive capture) | 0.970 | 1.34 |

The large shared-GPU difference already exists while the apps are still. Both desktop baselines exceed GitComet scrolling. The apps have different window coverage and static layouts; compositor/background activity can vary. Those observations prevent attributing the whole-GPU watt difference to the app or its renderer, and baseline subtraction would not isolate app watts.

All per-run values, idle phases, four adjacent Fork-minus-GitComet contrasts and metric availability are in `analysis.json`. Missing or partially readable process GPU counters remain unavailable, never zero. WindowServer attribution may be unavailable because one client has empty AppUsage. A Fork GPU counter that is unavailable cannot support a CPU-only/no-GPU conclusion.

The observer is a separate process; its CPU is reported and never added to app CPU. Optional CUA process accounting can be unavailable under unprivileged process access. Automation/compositor/background work is present in shared whole-GPU measurements. Baselines are descriptive desktop snapshots, not subtraction controls that isolate app watts.

GPU execution milliseconds are not percent of peak GPU compute. GPU Energy Model watts include the whole GPU and all users; they exclude unvalidated CPU/system energy. Raw CPU-energy counters are retained but not validated or analyzed. Battery, socket and total-system energy were not measured. A lower value accompanied by different work/output is not an efficiency win.

GPU process totals can recompose across unrecorded client lifetimes without a detectable aggregate decrease. Calls are sequential; acquisition spans report timing skew. The analyzer integrates only complete adjacent1Hz intervals inside phase bounds, so actual exposure is shorter than nominal phase duration.

Four protected-folder repositories were excluded from both apps before main acquisition after a setup permission/file-open stall; no permission settings changed. This is a40-repository comparison, not the real264-repository session. Original sessions and private repo paths are omitted.

Saved-data reproduction (Python standard library only; no apps/native calls):

```sh
python3 analyze.py series manifest.json --out reanalysis.json
```

`reanalysis.json` has the same numeric results; locally resolved paths can differ. `sample.py` and `perf_macos.py` are collector source provenance, not required for reanalysis. Raw telemetry/events/CUA numeric outputs are copied unchanged. Profiles, repository identities/paths, app logs, screenshots, tool conversation content and private orchestration are omitted. Public controls expose only counts/boolean preservation witnesses and native geometry/display settings.

OpenAI Codex assisted the investigation, collection tools, analysis, independent agent reviews and report. Published at the reporter’s explicit request; agent review is not human review.
