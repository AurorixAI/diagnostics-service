#!/usr/bin/env python
"""Root-cause study: summarise variant arms against a base arm (paired, all grades + pooled ALL).

  python tools/rootcause_summary.py --base base2 --variants OFF1 CONF2 OC OCT OCTB OC15 \
         --stage stage2 [--progress-log PATH]

Reads tools/sim_results/rootcause_<tag>_G<n>.json (written by rootcause_run.py run) and writes
tools/sim_results/rootcause_<stage>_summary.json + .txt.

Every metric is variant - base with a 95% percentile CI from the paired bootstrap of cat_sim.paired_bootstrap
(students resampled, same index in both arms; gap-student metrics resample gap students, gap-free metrics
gap-free students, separately).  The net signals are  sig_c = detect_cause(gap) - fp(no gap)  and
sig_r = detect_root(gap) - fp(no gap); gap and gap-free students are resampled separately for them too.
ALL = the 7 grades pooled (one student = one record).  A star marks a CI that excludes 0.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cat_sim  # noqa: E402
from rootcause_run import GRADES, RESULTS, load_arm, pooled  # noqa: E402

# (key in paired_bootstrap output, label, scale, fmt)
COLUMNS = [
    ("acc_category", "acc3", 100, "{:+.1f}"), ("acc_status5", "acc5", 100, "{:+.1f}"),
    ("rmse_theta", "RMSE", 1, "{:+.3f}"), ("len_mean", "len", 1, "{:+.2f}"), ("len_p90", "p90", 1, "{:+.1f}"),
    ("hit_max_items", "maxit", 100, "{:+.1f}"), ("covered_all_pct", "cover", 1, "{:+.1f}"),
    ("gap_topic_named", "topic", 100, "{:+.1f}"), ("detect_named", "named", 100, "{:+.1f}"),
    ("detect_cause", "cause", 100, "{:+.1f}"), ("detect_root", "root", 100, "{:+.1f}"),
    ("confirmed_gap_is_G", "confG", 100, "{:+.1f}"), ("fp_nogap", "fp", 100, "{:+.1f}"),
    ("scan_triggered_gap", "scan_g", 100, "{:+.1f}"), ("scan_triggered_nogap", "scan_ng", 100, "{:+.1f}"),
    ("ds_budget_exhausted", "budexh", 100, "{:+.1f}"), ("deep_scan_items", "ds_items", 1, "{:+.2f}"),
    ("signal_cause", "sig_c", 100, "{:+.1f}"), ("signal_root", "sig_r", 100, "{:+.1f}"),
]


def signals(ra, rb, n_boot=2000, seed=12345):
    """sig_c / sig_r (B - A) with a CI; gap and gap-free students resampled separately."""
    A, B = cat_sim.per_student_matrix(ra), cat_sim.per_student_matrix(rb)
    g = A["has_gap"]
    gi, ni = np.flatnonzero(g), np.flatnonzero(~g)
    rng = np.random.default_rng(seed + 1)
    gidx = gi[rng.integers(0, len(gi), (n_boot, len(gi)))]
    nidx = ni[rng.integers(0, len(ni), (n_boot, len(ni)))]
    out = {}
    for name, key in (("signal_cause", "cause"), ("signal_root", "detected")):
        a0 = A[key][gi].mean() - A["fp"][ni].mean()
        b0 = B[key][gi].mean() - B["fp"][ni].mean()
        d = (B[key][gidx].mean(1) - B["fp"][nidx].mean(1)) - (A[key][gidx].mean(1) - A["fp"][nidx].mean(1))
        lo, hi = (float(x) for x in np.percentile(d, [2.5, 97.5]))
        out[name] = {"A": float(a0), "B": float(b0), "diff": float(b0 - a0), "ci95": [lo, hi],
                     "excludes_0": bool(lo > 0 or hi < 0)}
    return out


def compare(ra, rb, n_boot):
    res = cat_sim.paired_bootstrap(ra, rb, n_boot)
    res.update(signals(ra, rb, n_boot))
    res["ds_unconfirmed_mean_B"] = float(np.mean([r.get("ds_unconfirmed", 0) for r in rb]))
    res["identical_to_base"] = all(
        {k: v for k, v in x.items() if k != "ds_unconfirmed"} == {k: v for k, v in y.items() if k != "ds_unconfirmed"}
        for x, y in zip(ra, rb))
    return res


def fingerprints(log: Path):
    """tag -> set of content fingerprints seen before/after its runs (from the driver's progress log)."""
    seen = {}
    if not log or not log.exists():
        return seen
    for line in log.read_text().splitlines():
        m = re.match(r"=== (\S+) .*?fp_(?:before|after): (.*)$", line)
        if m:
            seen.setdefault(m.group(1), set()).add(m.group(2).strip())
    return seen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--variants", nargs="+", required=True)
    ap.add_argument("--stage", default="stage2")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--progress-log", type=Path)
    a = ap.parse_args()

    problems, results, overrides, runtimes = [], {}, {}, {}
    fps = fingerprints(a.progress_log)
    base_fp = fps.get(a.base, set())
    if len(base_fp) > 1:
        problems.append(f"content DB changed while running {a.base}")
    for tag in a.variants:
        if fps.get(tag) and (len(fps[tag]) > 1 or fps[tag] != base_fp):
            problems.append(f"content DB differs between {a.base} and {tag} runs (fingerprints {len(fps[tag])})")
    base_arms = {g: load_arm(a.base, g) for g in GRADES}
    missing = [g for g, d in base_arms.items() if not d]
    if missing:
        problems.append(f"base {a.base} lacks grades {missing}")
    for tag in a.variants:
        arms = {g: load_arm(tag, g) for g in GRADES}
        per = {}
        pair_b, pair_v = [], []
        for g in GRADES:
            b, v = base_arms.get(g), arms[g]
            if not (b and v):
                problems.append(f"{tag}: grade {g} missing")
                continue
            per[f"G{g}"] = compare(b["arms"]["A"]["students"], v["arms"]["A"]["students"], a.n_boot)
            per[f"G{g}"]["runtime_s"] = (v.get("rootcause") or {}).get("runtime_s")
            pair_b.append((g, b)); pair_v.append((g, v))
        if len(pair_b) > 1:
            per["ALL"] = compare(pooled(pair_b), pooled(pair_v), a.n_boot)
            per["ALL"]["runtime_s"] = sum(((v.get("rootcause") or {}).get("runtime_s") or 0) for _, v in pair_v)
        results[tag] = per
        first = next((d for d in arms.values() if d), None)
        overrides[tag] = (first or {}).get("rootcause", {}).get("setting_overrides")
        runtimes[tag] = per.get("ALL", {}).get("runtime_s")

    lines = [f"{a.stage}: variant - base ({a.base}), delta[95% CI paired bootstrap]; % points for rates "
             "(RMSE, len, p90, ds_items absolute; cover = pct points); * = CI excludes 0",
             "sig_c = cause(gap) - fp(no gap); sig_r = root(gap) - fp(no gap)",
             "problems: " + ("; ".join(problems) if problems else "none")]
    for tag, per in results.items():
        lines += ["", f"=== {tag} {overrides[tag]}   (runtime {runtimes[tag]:.0f}s)" if runtimes[tag] else f"=== {tag} {overrides[tag]}"]
        grades = list(per)
        lines.append(f"{'metric':9s}" + "".join(f"{g:>26s}" for g in grades))
        for key, label, scale, f in COLUMNS:
            cells = []
            for g in grades:
                x = per[g].get(key)
                if x is None:
                    cells.append("n/a")
                    continue
                nd = 3 if f == "{:+.3f}" else (2 if f == "{:+.2f}" else 1)
                s = (f.format(x["diff"] * scale)
                     + f"[{x['ci95'][0] * scale:+.{nd}f},{x['ci95'][1] * scale:+.{nd}f}]"
                     + ("*" if x["ci95"][0] > 0 or x["ci95"][1] < 0 else ""))
                cells.append(s)
            lines.append(f"{label:9s}" + "".join(f"{c:>26s}" for c in cells))
        lines.append(f"{'unconf/s':9s}" + "".join(f"{per[g]['ds_unconfirmed_mean_B']:>26.3f}" for g in grades)
                     + "   (variant: probed skills left unconfirmed per student)")
        ident = [g for g in grades if g != "ALL" and per[g]["identical_to_base"]]
        if ident:
            lines.append(f"identical to base: {ident}")
    out_json = RESULTS / f"rootcause_{a.stage}_summary.json"
    json.dump({"description": f"{a.stage}: variant - base ({a.base}), paired bootstrap 95% CI ({a.n_boot}); rates stored as "
                              "fractions; signal = detect_X(gap) - fp(no gap); gap and gap-free students resampled separately",
               "base": a.base, "overrides": overrides, "problems": problems, "runtime_s": runtimes, "results": results},
              open(out_json, "w"), ensure_ascii=False, indent=1)
    out_txt = out_json.with_suffix(".txt")
    out_txt.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
