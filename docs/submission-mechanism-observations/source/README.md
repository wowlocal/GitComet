# Exact source reconstruction

The dataset's documentation branch base is GitComet
`14b3cba1a8fcd51ae6a32e8bbc385556625bf5b2`. That is distinct from the app
source used to build this earlier probe:

| Component | Repository | Exact base | Complete overlay |
| --- | --- | --- | --- |
| App | [Auto-Explore/GitComet](https://github.com/Auto-Explore/GitComet) | `ad5df1d185c1a8805870bffcfde592d5e3ce355a` | `app-full.patch` |
| Framework | [Havunen/gpui-ce](https://github.com/Havunen/gpui-ce) | `c55d73659dd6560d3e70281056f841e6d366c0e5` | `framework-full.patch` |

The framework full overlay includes production PR #47 at
`aad11809345380e3ae2d79f6cfcfc5aaf2af4edc`, the frozen common observer and the
additional submission probe. Do not apply PR #47 again. Each `*-full.patch`
reconstructs the exact final source from its base. `*-baseline.patch` followed
by `*-delta.patch` is the equivalent decomposition, not additional patches to
apply after the full overlay. The per-file and overlay hashes are frozen in
[source-manifest.json](source-manifest.json).

Use adjacent checkouts named `GitComet-submission-probe` and
`gpui-ce-submission-probe`; the app's 22 relative Cargo path overrides point to
that framework directory. Check out the exact bases, then `git apply --check`
and `git apply` the corresponding full patches. Do not edit Cargo's shared
checkout cache. An isolated target directory avoids overwriting other builds.

The recorded release build used Rust 1.99.1 / LLVM 23.1.1 on
`aarch64-apple-darwin`, the source workspace's release profile, two background
build jobs and `--release --locked --offline -p gitcomet --features ui-gpui,gix
--bin gitcomet`. The portable command and full toolchain string are in
[build-provenance.json](build-provenance.json). Offline reproduction assumes
the recorded lock's dependencies are already available. Signing is
machine-specific; a reconstructed source tree is not a promise of a
byte-identical signed executable. The binary is not distributed here.

Revision 1 failed release compilation because the observer getter
`preferredFrameRateRange()` required its generated `CAFrameRateRange` feature.
Revision 2 enabled only that binding feature; no scheduling or runtime policy
was changed. The final release passed and was signed. The original failed log
hash and revision record remain in the sanitized source manifest.

Sixteen exact-recorder-module unit tests passed using a standalone `rustc
--test` harness linked to the release extern libraries. That result is scoped
to the recorder module, **not** a full framework Cargo/native lifecycle suite.
The full workspace attempts were blocked by external-workspace dev-dependency
selection, an older default toolchain and an interrupted separate dependency
graph. Final commands, library hashes, warnings and outcomes are retained in
[recorder-tests.json](recorder-tests.json) and its sanitized log. The experiment
did not claim passing tests from the interrupted attempts.

The numeric observer's base measurement helper is
`scripts/profiling/perf_macos.py` at the exact app base. The acquisition
controller is machine-specific and is not published: it contains private
profile/repository locations. Its numeric scenario is included in each run;
the protocol and sanitized manifests record its controls and validation.

The framework backport preserves the source attribution to Steve Shreeve and
Anthony Eid and [Zed #65472](https://github.com/zed-industries/zed/pull/65472).
Framework changes remain Apache-2.0; see [LICENSE-GPUI-APACHE](LICENSE-GPUI-APACHE).
The app changes and these GitComet analysis scripts follow the repository's
AGPL-3.0-only license. Exact source is provided for review and reproduction;
this export is not a request to merge the private observer into the framework.
