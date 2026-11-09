# macOS Metal submission observations

This saved dataset contains one confirmation and its **excluded pilot** of an
instrumented GitComet history-scroll replay. It investigates drawable submission
outcomes with the proposed `CAMetalDisplayLink` backport in
[gpui-ce PR #47](https://github.com/Havunen/gpui-ce/pull/47). The PR remains Draft.

The confirmation records zero/nonpresented drawable callbacks even though every
assigned estimated presentation target is unique. This does not establish why
those drawables were not reported as displayed. In particular, the probe does
not record the exact deferred `drawable.present()` call time.

- [Findings and denominators](findings.md)
- [Method, timestamp meanings and limits](method.md)
- [Frozen manifest](manifest.json)
- [Export transformations and original hashes](export-provenance.json)
- [Independent raw audit](independent-raw-audit.json)
- [Source, build and licensing provenance](source/README.md)

`runs/confirmation/` and `runs/pilot-excluded/` each contain the raw native
records, app timing, numeric observer measurements, exact programmatic scenario
and complete per-call/per-update analysis. The pilot passed acquisition checks
but is not a second confirmation or a matched control. It is retained to make
the complete acquisition history available.

Reproduce the saved-data checks with Python 3, from this directory:

```sh
python3 analysis/verify.py
```

The verifier checks every published file hash, reruns the unchanged registered
analyzer for both captures, and reconstructs the independent raw audit. It
performs no app launch, compilation, native sampling or network request.

Raw native records and all six source patches are unchanged. App timing replaces
only repository-path strings with `repository-under-test`. Observer measurements
retain every numeric value and replace the battery-status description with
`AC`. Private profiles, repository identities, session/index hashes, absolute
home paths, signing identity, screenshots and application logs are omitted.
All changed export fields and original/exported hashes are recorded.

This is a single-arm, observer-instrumented **programmatic** mechanism probe.
It does not measure a stock-versus-fix effect, instrumentation overhead, energy
efficiency, physical trackpad smoothness or end-to-end input latency. Zero,
missing, ambiguous and positive presentation outcomes remain distinct. No
scheduler, compositor or driver cause is claimed.

Prepared with OpenAI Codex and published at the reporter’s explicit request.
The framework PR remains a draft pending maintainer review. Framework patch
attribution and its Apache-2.0 license are preserved separately from GitComet’s
AGPL-3.0-only source.
