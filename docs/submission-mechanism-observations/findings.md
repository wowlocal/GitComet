# Confirmation findings

The confirmation reproduces zero/nonpresented drawable callbacks with **unique
assigned estimated presentation targets**. It does not support the specific
duplicate-target hypothesis. It does not identify the cause of nonpresentation:
exact enqueue, commit, scheduling and deferred `drawable.present()` call times
were not recorded. These observations do not justify a scheduling change alone;
gpui-ce PR #47 remains Draft.

Both finite captures passed acquisition checks and independent raw joins. The
pilot has 20,622 sequence-bearing records; the confirmation has 20,292. Each has
one arm, contiguous ordered records, a duration-complete footer, zero drops and
zero marker overflow. Every submitted call has exactly one matching submit-end,
GPU-completion and presentation callback. All recorded GPU statuses are
completed (4), with available GPU host timestamps and no ambiguous or missing
joins. There are no actual native-input records. Both replays contain 1,442 app
inputs, 1,440 scenario markers and the expected 12 logical endpoints. All Metal
updates report OS defaults: latency 2 and frame-rate range 0/0/0.

| Predeclared scrolling scope | Excluded pilot | Confirmation |
| --- | ---: | ---: |
| Exposure | 11.767270 s | 11.766628 s |
| Updates/submissions by callback/begin time | 1,413/1,413 | 1,412/1,412 |
| Positive / zero-or-not-presented outcomes for those submissions | 942/471 | 880/532 |
| Duplicate assigned estimated target groups | 0 | 0 |
| Unique positive actual display timestamps in that interval | 940 | 881 |
| Actual display events / selected wall second | 79.88 | 74.87 |
| Median / p95 actual timestamp gap | 16.66646/16.66671 ms | 16.66662/16.66675 ms |
| Maximum actual timestamp gap | 16.66892 ms | 16.67133 ms |

The outcome and display rows intentionally use different boundaries.
Submissions are selected by their begin time; actual displays are selected by
positive `presentedTime`. Joins use the whole capture, including callbacks
outside the selected interval. Therefore 880 positive outcomes for selected
confirmation submissions and 881 actual display timestamps inside the same
wall interval are consistent. These are drawable/display-event counts, not
verified new visual frames or physical-trackpad FPS.

In the confirmation scrolling scope every CPU submission path returned before
its assigned CPU presentation deadline: the closest return was 2.175 ms early.
Every GPU command ended before that deadline too, at least 0.551 ms early, and
before its estimated display target. Among the 532 zero outcomes specifically,
the CPU path returned at least 2.317 ms early and the GPU ended at least
0.889 ms early. These are relative timings. They do **not** prove that the
deferred drawable presentation method itself was called before its deadline.
GPU completion before the CPU deadline is neither a required contract nor a
sufficient guarantee of display.

Assigned estimated targets advance at a median 8.333333 ms in each scope.
Across the entire captures all 2,404 pilot targets and all 2,399 confirmation
targets are distinct per window. Capture-wide totals include idle/setup work:
2,396 submissions with 795 zero outcomes in the pilot, and 2,392 submissions
with 837 zero outcomes in the confirmation. The roughly 60-second capture
average is not scrolling cadence; it includes intentional long idle dwells.

The eight predeclared source-active windows total 4.601196 seconds and remain
separate when calculating gaps. They contain 552 submissions each, with 194
pilot and 214 confirmation zero outcomes. Unique actual displays are 361 and
335, respectively. The confirmation has 327 adjacent known-pose pairs, 35 held
within 0.01 px, and no unknown displayed poses. It has 292 changed actual scene
pairs; 111 changes came from submissions whose revision was reused relative to
the previous **submission**. A reused submission is therefore not synonymous
with a repeated actually displayed scene. These source windows are a distinct
predeclared scope, not a strict subset of the trimmed scrolling interval.

The registered analyzer and the independent raw audit agree on joins, exact
target groups, phase clocks, scopes, outcomes and displayed-pose pairs. Their
full tables and hashes are published beside the raw data. The packaged binary
was independently hashed after acquisition and matches the frozen build record.
This export involved only saved-file analysis, without new acquisition.

The probe has no matched stock arm or instrumentation-overhead control. It
cannot establish a PR effect, explain earlier CPU differences, measure energy,
or validate user feel. Keep the earlier stock/fix comparison separate. The
association between early-completed work and zero presentation remains an open
mechanism question, with no OS/driver/compositor attribution.
