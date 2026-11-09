# Independent resume bookkeeping review

No blocking finding for resuming the current series after external build/game activity is quiet. Reviewed only saved source and manifest files; no app, build or live measurement was started.

The current manifest retains valid ordinals 1 (stock) and 2 (fixed), plus failed ordinal 3 (fixed) with its startup focus/readiness failure and absent-plan/capture consequences. The runner skips valid ordinals, retries ordinal 3 as `03-fixed-attempt2`, preserves the original failed directory and appends every completed attempt to the same manifest. The expected remaining valid conditions are fixed, stock, fixed, stock, stock, fixed.

Resume checks the existing order, real-session hash, copied profile hash, input plan hash and selected repository HEAD/status/index identity. The manifest's viewport/environment controls survive resume. Independently checked that current build metadata matches the binary identities in the retained valid runs:

- Stock: `600bfe5e5db6969aa99d503e9a78ef984bc2ec1a61db0e6bd4308dd8627fe2bf`.
- Fixed: `f23c14a83b84bf542cadd0d8fee060ff53b4e1f3f987c7dc7180e6ed410b08aa`.

The runner still verifies the launched bundle against that build metadata. No rebuild or condition change is introduced by resume.

Diffing against `run-before-resume.py` and `analyze-before-resume.py` confirms the changes are orchestration and bookkeeping: resume loading, attempt suffixes, skipping already valid ordinals, preserving invalid attempts in analysis, and asserting exactly eight valid ordinals in the declared A B B A B A A B order. Metric definitions, core selection, telemetry integration, percentile functions and paired signs are unchanged.

The analyzer excludes invalid attempts from conditional foreground-ready timing summaries, explicitly lists them, and requires valid ordinals 1–8 exactly once and in planned condition order. The startup failures must remain a separate reported outcome, including their condition and the interrupted/resumed sequence; the timing result cannot be described as an unconditional startup/reliability result.

A resume interruption extends the time between observations. The final report should retain run timestamps, environmental witnesses and the interruption reason. These remain four valid timing replicates per condition, not eight independent uninterrupted randomized observations.
