# Common stock-versus-PR47 instrumentation review

Independent read-only source review of the local framework/app benchmark worktrees and `prepare.py`. No builds, tests, UI actions, or profilers were run by this reviewer. Only this local review artifact was written.

## Finding and correction

**Resolved before compilation:** the original factory delimited the native-scroll observer with the next `let Some(` in the old window source. That copied 434 lines, including unrelated callbacks, into `handle_view_event`. The original stock patch `81b25df44bb54bfe5a34e0d1a9a5317031dd57e934332a8b9616b9a87ac5a2bb` is invalid benchmark material.

The parent changed the endpoint to the first `match native_event_type {`, added a maximum 25-line/one-call/no-extern assertion, and recreated all touched framework files from pristine c55 before reinjecting the observer. I re-read the regenerated diff: `window.rs` now adds exactly 19 lines for renderer window identification and native input observation. No unrelated window callbacks remain in that overlay.

**No remaining concrete instrumentation correctness finding in the final stock/fixed sources.** The fixed-condition output has now been materialized and compared with saved stock sources and the exact PR47 commit. The later common addition of `objc2-core-foundation` enables the observer's `CACurrentMediaTime` binding; it changes no Rust observer code. The failed initial binding build is not benchmark material.

## Final observer-parity proof

I removed only the identified observer fields, hooks, module reexports, and binding features **in memory**, then compared the remaining source bytes against the appropriate production Git blobs. The union of observer/PR files comprises 12 paths per condition: all 24 checks matched exactly, with stock reconstructing c55 and fixed reconstructing aad1180. Saved stock-only unchanged files are represented by their base Git blobs and recorded stock patch.

The complete recorder, renderer submission/presented-handler block, GPU-completion-handler block, and native-scroll observer are byte-identical between saved stock and current fixed source. The saved stock application manifest, lockfile, and scenario driver are also byte-identical to the fixed application's files. Foundation is already a PR production dependency in the fixed condition; adding it for the stock observer gives both application builds the same resolved common dependency graph.

The fixed full patch now includes the new production `display_link.rs` after its intent-to-add registration. Its current hash is `2a51e6403d87617b14ecc2af7a54c2b0a73688229eb0a66d31c1b356ef948377`; the earlier pre-registration `86d643...` hash did not cover that new file and must not identify the final build. Exact checks and hashes are saved in `instrumentation-parity.json` beside this review.

## Source isolation

- Application HEAD is `ad5df1d185c1a8805870bffcfde592d5e3ce355a`. The only application Rust change is `scenario_driver.rs`: bounded absolute-offset packet replay, explicit capture arming, numeric endpoint/loaded-window witnesses, and a validation test. The existing scheduled-input loop is factored without changing its dispatch/witness behavior.
- Application manifest/lock changes select the same owned local GPUI workspace and include the observer's Foundation dependency. Application production views, scrolling logic, and draft742 changes are absent.
- The stock framework production source is c55d73659dd6560d3e70281056f841e6d366c0e5. The factory obtains fixed production files directly from aad11809345380e3ae2d79f6cfcfc5aaf2af4edc, then applies the same observer. It leaves the common app patch intact during that transition.
- The observer does not call frame-rate/latency setters, alter link wake/pause behavior, or replace drawable acquisition/presentation. The copied recorder contains unused experiment-option definitions, but no corresponding production override hooks are installed in this overlay.

## Native ownership and recording

- Presented callbacks capture only numeric `Arc<Submission>` metadata, never the drawable that owns the callback. GPU completion callbacks likewise retain only that metadata, and read command-buffer status/GPU host timestamps from the documented live completed-handler borrow. No new buffer/drawable retain cycle is introduced.
- Existing instance-buffer completion handling and both transaction/convenience presentation calls remain unchanged. Drawable identity is read only while native ownership is valid.
- Recording is opt-in, numeric, mutex-protected, bounded to 32,768 records and 16 marker windows, with finite capture duration. Per-event paths do not format or write files. The background worker creates a new destination, records explicit waiting/armed/completed status, and reports overflow/drops. A header failure cannot race arming to revive a finished recorder.
- Explicit scenario arming is separate from AppKit input. It arms the same recorder once at prefill; later packet plans do not restart its deadline. Native input observation remains distinguishable so real scrolling can invalidate a synthetic trial.
- The disabled path avoids native timing getters/handler allocation after the opt-in check. Both builds pay the same observer implementation when enabled; its per-frame cost is still instrumentation overhead, so the stock build must be identified as instrumented stock rather than an untouched release.

## Measurement limits

- `submit_begin` is recorded **after drawable acquisition** in both conditions. Its interval measures later CPU encoding/presentation work, and excludes stock `nextDrawable` blocking. Use existing full platform-present/UI-probe timing when discussing that blocking cost.
- The recorder's new/cached-scene flag compares prior submissions, not prior positive actual displays. Actual displayed cadence must use positive `presentedTime`, with skipped/zero/tail records retained separately as the protocol specifies.
- Endpoint witnesses report application logical scroll state around each packet plan; they are not measurements of every displayed pose. Packets are synthetic GPUI events with ordinary `Moved` phase, not fabricated hardware momentum metadata.
- Common instrumentation supports a fair controlled comparison but cannot turn a programmatic workload into a complete physical-trackpad feel benchmark. Native callback completion and energy/pacing arithmetic remain runtime validation, outside this source review.

## Verified regenerated stock snapshot

| Item | SHA-256 |
| --- | --- |
| Final stock framework tracked patch | `c44c7b985dfd5bff177814fee7d9b495714976360079c773acf3339c0c945b58` |
| Final fixed full framework tracked patch | `2a51e6403d87617b14ecc2af7a54c2b0a73688229eb0a66d31c1b356ef948377` |
| Common app patch | `da76c22f4de9cc7ab5ea9734d50f05ab31068c65f8254185b102d47ef421a620` |
| Native recorder source | `06d8989ee36b78d1b57d0e2d9ade897699bbdae265422eaedb0d1ba5aee177d9` |
| Final factory `prepare.py` | `26945ac02f4077fd28113a76f11832ffcc468f008b68307787ee9b314f46c655` |
| Common scenario driver source | `8622c837aabf18e41b90bd13f16224ecf4de3d40cbd46db3010a04605cd152a4` |

The final stock patch matches its saved source record; the fixed full patch, common app patch, and recorder were recomputed from the current owned worktrees. Refreshing the fixed source record to the full patch hash is provenance maintenance, not a source change.
