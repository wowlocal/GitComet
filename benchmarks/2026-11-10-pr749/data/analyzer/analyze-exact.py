"""Saved-data analysis. Actual presentation cadence and process CPU; no energy."""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import math
import statistics


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def stats(values):
    v = sorted(x for x in values if x is not None and math.isfinite(x))
    if not v:
        return {"n": 0, "median": None, "p95": None, "p99": None, "max": None}
    def q(p):
        at = (len(v) - 1) * p
        lo, hi = math.floor(at), math.ceil(at)
        return v[lo] + (v[hi] - v[lo]) * (at - lo)
    return {"n": len(v), "min": v[0], "mean": statistics.mean(v),
            "median": q(.5), "p95": q(.95), "p99": q(.99), "max": v[-1]}


def window(visible, lo, hi):
    selected = [r for r in visible if lo <= r["presented_s"] <= hi]
    times = sorted(set(r["presented_s"] for r in selected))
    gaps = [(b - a) * 1000 for a, b in zip(times, times[1:])]
    by_time = {}
    for item in selected:
        by_time.setdefault(item["presented_s"], item)
    ordered = [by_time[at] for at in times]
    repeated = sum((b["window"], b["scene_revision"]) == (a["window"], a["scene_revision"])
                   for a, b in zip(ordered, ordered[1:]))
    return {"same_scene_revision_pairs": repeated,
            "same_scene_revision_limit": "Recorded revision identity only; not verified pixel equality. All presentations remain in the denominator.",
            "lo_ca_s": lo, "hi_ca_s": hi, "exposure_s": hi-lo,
            "presentations": len(times), "duplicate_timestamps": len(selected)-len(times),
            "rate_hz": len(times)/(hi-lo), "interval_ms": stats(gaps), "gaps_ms": gaps,
            "over_12_5_ms": sum(g > 12.5 for g in gaps)}


def analyze_run(run, plan):
    measurement = json.loads((run / "measurement.json").read_text())
    assert measurement["verification"]["valid"] is True
    frames, native = rows(run / "frames.jsonl"), rows(run / "native.jsonl")
    inputs = [r for r in frames if r["event"] == "scenario_input"]
    scrolls = [r for r in native if r["event"] == "scenario_scroll"]
    assert len(inputs) == 1442 and len(scrolls) == 1440
    expected = [p["delta_px"] * (1 if cycle % 2 == 0 else -1)
                for cycle in range(6) for p in plan["packets"]]
    assert all(abs(r["dy"]-delta) < 1e-6 and r["dx"] == 0 for r, delta in zip(scrolls, expected))
    offsets = [r["at_s"] - item["unix_ms"]/1000 for r, item in zip(scrolls, inputs[2:])]
    clock = statistics.median(offsets)
    residuals = [(value-clock)*1000 for value in offsets]
    join_max_abs_ms = max(abs(value) for value in residuals)
    begins = {r["detail"]["name"]: r for r in frames
              if r["event"] == "scenario_phase" and r["detail"]["state"] == "begin"}
    ends = {r["detail"]["name"]: r for r in frames
            if r["event"] == "scenario_phase" and r["detail"]["state"] == "end"}
    visible = sorted([r for r in native if r["event"] == "presented"
                      and r["did_present"] and r["presented_s"] > 0], key=lambda r: r["presented_s"])
    cores = []
    for cycle in range(4):
        origin = scrolls[(cycle+2)*240]["at_s"]
        for index, core in enumerate(plan["motion_core_windows"]):
            item = window(visible, origin+core["start_us"]/1e6, origin+core["end_us"]/1e6)
            item.update(cycle=cycle, burst=index)
            cores.append(item)
    gaps = [value for core in cores for value in core["gaps_ms"]]
    cadence = stats(gaps)
    cadence.update(exposure_s=sum(c["exposure_s"] for c in cores),
                   presentations=sum(c["presentations"] for c in cores),
                   empty_windows=sum(c["presentations"] == 0 for c in cores),
                   same_scene_revision_pairs=sum(c["same_scene_revision_pairs"] for c in cores),
                   over_12_5_fraction=sum(g > 12.5 for g in gaps)/len(gaps) if gaps else None)
    lo = begins["replay-0"]["unix_ms"] + 300
    hi = ends["replay-3"]["unix_ms"] - 300
    # A native CA/Unix bracket avoids treating preemptible input-record latency as clock error.
    anchors = measurement.get("clock_anchors", [])
    anchor_offsets = [a["ca_s"]-(a["unix_before_s"]+a["unix_after_s"])/2 for a in anchors]
    clock_ok = (len(anchors) == 2 and [a.get("event") for a in anchors] == ["ready", "after_scroll"]
                and all(a.get("anchor_valid") is True and 0 <= a["unix_after_s"]-a["unix_before_s"] <= .002 for a in anchors)
                and max(anchor_offsets)-min(anchor_offsets) <= .002)
    samples = [(s, s["app_cpu"]) for s in measurement["samples"] if s.get("app_cpu")
               and lo <= s["unix_ms"] <= s["app_cpu"]["unix_ms"] <= hi]
    sample_ok = (len(samples) >= 4 and all(
        b[1]["cpu_s"] >= a[1]["cpu_s"] and b[1]["unix_ms"] > a[1]["unix_ms"]
        for a, b in zip(samples, samples[1:])) and all(
        0 <= item["unix_ms"]-sample["unix_ms"] <= 5 for sample, item in [samples[0], samples[-1]]))
    cpu = {"available": False, "ms_per_presentation": None,
           "reason": "Missing/unbounded native clock brackets or CPU read samples", "samples": len(samples),
           "input_record_to_marker_residual_ms": stats(residuals), "join_max_abs_ms": join_max_abs_ms}
    if clock_ok and sample_ok:
        cpu_clock = statistics.median(anchor_offsets)
        anchor_error_s = max((a["unix_after_s"]-a["unix_before_s"])/2 for a in anchors) + (max(anchor_offsets)-min(anchor_offsets))/2
        (first_row, first), (last_row, last) = samples[0], samples[-1]
        first_ms = (first_row["unix_ms"]+first["unix_ms"])/2
        last_ms = (last_row["unix_ms"]+last["unix_ms"])/2
        first_error_s = (first["unix_ms"]-first_row["unix_ms"])/2000+anchor_error_s
        last_error_s = (last["unix_ms"]-last_row["unix_ms"])/2000+anchor_error_s
        ca_lo, ca_hi = first_ms/1000+cpu_clock, last_ms/1000+cpu_clock
        cpu_window = window(visible, ca_lo, ca_hi)
        inner = window(visible, ca_lo+first_error_s, ca_hi-last_error_s)
        outer = window(visible, ca_lo-first_error_s, ca_hi+last_error_s)
        cpu_ms = (last["cpu_s"]-first["cpu_s"])*1000
        exposure_s = (last_ms-first_ms)/1000
        cpu.update(available=True, reason=None, first_unix_ms=first_ms, last_unix_ms=last_ms,
                   exposure_s=exposure_s, process_cpu_ms=cpu_ms, percent_one_core=cpu_ms/exposure_s/10,
                   presentations=cpu_window["presentations"],
                   presentation_count_bounds=[inner["presentations"], outer["presentations"]],
                   boundary_uncertainty_ms=[first_error_s*1000, last_error_s*1000],
                   ms_per_presentation=cpu_ms/cpu_window["presentations"] if cpu_window["presentations"] else None,
                   native_clock_offset_s=cpu_clock,
                   native_anchor_drift_ms=(max(anchor_offsets)-min(anchor_offsets))*1000,
                   boundary_limit="Counter value acquired within recorded read bracket; nominal presentation count uses midpoint and reports inner/outer count bounds. No interpolation/energy claim.")
    full_lo, full_hi = scrolls[480]["at_s"]+.3, scrolls[-1]["at_s"]-.3
    submits = [r for r in native if r["event"] == "submit_begin" and full_lo <= r["at_s"] <= full_hi]
    present_map = {(r["window"], r["call"]): r for r in native if r["event"] == "presented"}
    gpu_map = {(r["window"], r["call"]): r for r in native if r["event"] == "gpu_completed"}
    outcomes = collections.Counter()
    for item in submits:
        key = item["window"], item["call"]
        p, g = present_map.get(key), gpu_map.get(key)
        outcomes["submissions"] += 1
        outcomes["missing_present_callback"] += p is None
        outcomes["zero_presented_time"] += p is not None and not (p["did_present"] and p["presented_s"] > 0)
        outcomes["missing_gpu_callback"] += g is None
        outcomes["gpu_errors"] += g is not None and g["status"] != 4
    dispatch = []
    for cycle in range(4):
        packet_rows = scrolls[(cycle+2)*240:(cycle+3)*240]
        origin = packet_rows[0]["at_s"]
        dispatch.extend((r["at_s"]-origin)*1000-p["at_us"]/1000
                        for r, p in zip(packet_rows, plan["packets"]))
    observer_ms = (measurement["observer_cpu_after"]["cpu_s"]
                   - measurement["observer_cpu_before"]["cpu_s"])*1000
    return {"path": str(run), "cadence": cadence, "cores": cores, "cpu": cpu,
            "dispatch_lag_relative_first_ms": stats(dispatch), "submission_outcomes": dict(outcomes),
            "observer_parent_cpu_ms_only": observer_ms, "observer_limit": "Python PID only; excludes ps/native helper children and app/native recorder work", "measurement_sha256": hashlib.sha256((run/"measurement.json").read_bytes()).hexdigest()}


METRICS = {"cpu_ms_per_presentation": ("cpu", "ms_per_presentation"),
           "interval_p95_ms": ("cadence", "p95"), "interval_p99_ms": ("cadence", "p99"),
           "interval_over_12_5_fraction": ("cadence", "over_12_5_fraction")}


def contrasts(runs):
    from scipy.stats import t
    pairs = []
    for index in range(0, len(runs), 2):
        pair = runs[index:index+2]
        assert len(pair) == 2 and {r["condition"] for r in pair} == {"before", "after"}
        a = next(r for r in pair if r["condition"] == "before")
        b = next(r for r in pair if r["condition"] == "after")
        values = {}
        for name, (category, key) in METRICS.items():
            va, vb = a[category][key], b[category][key]
            values[name] = vb-va if va is not None and vb is not None else None
        pairs.append({"ordinals": [a["ordinal"], b["ordinal"]], "after_minus_before": values})
    summaries = {}
    for name, (category, key) in METRICS.items():
        values = [p["after_minus_before"][name] for p in pairs]
        if any(v is None for v in values):
            summaries[name] = {"available": False, "reason": "Undefined outcome retained"}
            continue
        mean = statistics.mean(values)
        half = float(t.ppf(.975, len(values)-1))*statistics.stdev(values)/math.sqrt(len(values))
        deviations = []
        for condition in ["before", "after"]:
            observed = [r[category][key] for r in runs if r["condition"] == condition]
            median = statistics.median(observed)
            deviations.append(statistics.median(abs(v-median) for v in observed))
        summaries[name] = {"available": True, "paired_differences": values, "summary": stats(values),
                           "mean_95pct_t_ci": [mean-half, mean+half], "within_build_mad": deviations,
                           "directional_endpoint_gate": (mean-half > 0 or mean+half < 0)
                           and abs(statistics.median(values)) > max(deviations)}
    return pairs, summaries


def plot(runs, destination, ax_label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"before": "#ce5d62", "after": "#318fbc"}
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)
    for index in range(0, len(runs), 2):
        pair = sorted(runs[index:index+2], key=lambda r: r["condition"] == "after")
        for axis, category, key in [(axes[0], "cpu", "ms_per_presentation"), (axes[1], "cadence", "p99")]:
            values = [r[category][key] for r in pair]
            if all(v is not None for v in values):
                axis.plot([0, 1], values, color="#a5a8ad", alpha=.6, linewidth=.8)
                axis.scatter([0, 1], values, color=[colors[r["condition"]] for r in pair], s=30, zorder=3)
    axes[0].set_ylabel("Process CPU ms / actual presentation")
    axes[1].set_ylabel("Actual presentation interval p99 (ms)")
    for axis in axes[:2]:
        axis.set_xticks([0, 1], ["Before", "PR #749"])
        axis.grid(axis="y", alpha=.2)
    for r in runs:
        gaps = sorted(g for core in r["cores"] for g in core["gaps_ms"])
        if gaps:
            axes[2].step(gaps, [(i+1)/len(gaps) for i in range(len(gaps))], where="post",
                         color=colors[r["condition"]], alpha=.35, linewidth=1)
    axes[2].axvline(1000/120, color="#666", linestyle=":", linewidth=1)
    axes[2].set(xlabel="Actual interval (ms)", ylabel="Per-run cumulative fraction")
    axes[2].grid(alpha=.2)
    fig.suptitle(f"Isolated PR #749 · {ax_label} · 264 repositories · generated replay")
    fig.savefig(destination / "comparison.png", dpi=170)
    fig.savefig(destination / "comparison.svg")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    path = args.manifest.resolve()
    manifest = json.loads(path.read_text())
    assert manifest.get("ax") in ("normal", "forced") and manifest.get("native_observer") is True
    assert not manifest.get("profile_cpu"), "Sampled pilots cannot supply efficacy analysis"
    assert not manifest["pilot"] and len(manifest["order"]) == 16
    entries = [r for r in manifest["runs"] if r["valid"]]
    assert len(entries) == 16 and [r["ordinal"] for r in entries] == list(range(1, 17))
    assert [r["condition"] for r in entries] == manifest["order"]
    plan_path = Path(__file__).parent.parent / "stock-vs-fix/input-plan.json"
    assert hashlib.sha256(plan_path.read_bytes()).hexdigest() == manifest["input_plan_sha256"]
    plan = json.loads(plan_path.read_text())
    results = []
    for entry in entries:
        raw_measurement = json.loads((Path(entry["path"])/"measurement.json").read_text())
        assert raw_measurement["condition"] == entry["condition"] and raw_measurement["ordinal"] == entry["ordinal"], "Raw/manifest lineage mismatch"
        result = analyze_run(Path(entry["path"]), plan)
        result.update(condition=entry["condition"], ordinal=entry["ordinal"])
        results.append(result)
    pairs, summaries = contrasts(results)
    output = {"scope": __doc__, "ax": manifest["ax"], "manifest": str(path),
              "replicates": "Eight adjacent A/B run pairs; frames are not independent replicates",
              "inference_limit": "Per-endpoint exploratory CIs, not simultaneous family-wise claims; conditional on common app/native recording. No physical-motion, energy or multi-PR rank claim.",
              "invalid_attempts": [r for r in manifest["runs"] if not r["valid"]],
              "paired_contrasts": pairs, "summaries": summaries, "runs": results}
    destination = path.parent / "analysis.json"
    assert not destination.exists(), "Never overwrite analysis evidence"
    destination.write_text(json.dumps(output, indent=2) + "\n")
    plot(results, path.parent, manifest["ax"])
    print(json.dumps({"analysis": str(destination), "summaries": summaries}, indent=2))


if __name__ == "__main__":
    main()
