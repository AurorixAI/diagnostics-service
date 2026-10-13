#!/usr/bin/env python
"""Root-cause study, stage 0: run one arm of cat_sim on the fixed stand for all grades, and compare arms.

  # run an arm (default settings = the shipped defaults = variant OC15: offset 1.5, confirm probes 2);
  # the old baseline needs --setting DEEP_SCAN_PROBE_DIFFICULTY_OFFSET=0.0 --setting DEEP_SCAN_CONFIRM_PROBES=1
  # results -> tools/sim_results/rootcause_<tag>_G<n>.json
  python tools/rootcause_run.py run --tag base
  python tools/rootcause_run.py run --tag budget8 --setting DEEP_SCAN_SESSION_BUDGET=8 --grades 7 8
  python tools/rootcause_run.py run --tag base_ref --stand-set reference --grades 7 8 9 11   # earlier gap sets
  python tools/rootcause_run.py run --tag A0 --stand-set stand --workers 8     # stand A (default)
  python tools/rootcause_run.py run --tag B0s2 --stand-set B --seed 2          # stand B: 8 seeded gap L3 per grade (rootcause_stand_b.py), student seed 2

Stage-3a instrumentation (l3_visits, shadow_triggers, scan_log, ...) is written into every per-student record; metrics:
  python tools/rootcause_diag.py --tag A0 --stage stage3a

  # one-arm table / paired comparison variant vs base (JSON + compact text table)
  python tools/rootcause_run.py table --tag base
  python tools/rootcause_run.py compare --base base --variant budget8

The stand (tools/rootcause_stand.json) fixes gap L3 per grade, seed, n, gap-fraction, fail-p and depth.
The content DB is only read (DATABASE_URL from ../content-service/.env unless --content-db-url).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
DIAG = TOOLS.parent
STAND = TOOLS / "rootcause_stand.json"
RESULTS = TOOLS / "sim_results"
GRADES = [5, 6, 7, 8, 9, 10, 11]
sys.path.insert(0, str(TOOLS))

# (key in summarize(), label, kind) ; shown in tables
TABLE_KEYS = [
    ("acc_category", "acc3"), ("rmse_theta", "RMSE"), ("len_mean", "len"),
    ("gap_topic_named", "topic_named"), ("detect_named", "named"), ("detect_cause", "cause"), ("detect_root", "root"),
    ("confirmed_gap_is_G", "conf_is_G"), ("scan_triggered_gap", "scan_gap"), ("scan_triggered_nogap", "scan_nogap"),
    ("fp_nogap", "fp"), ("ds_budget_exhausted", "budget_exh"), ("hit_max_items", "max_items"),
]


def content_db_url(arg):
    if arg:
        return arg
    for line in (DIAG.parent / "content-service" / ".env").read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DATABASE_URL not found")


def out_path(tag, g):
    return RESULTS / f"rootcause_{tag}_G{g}.json"


def cmd_run(a):
    stand = json.load(open(STAND))
    P = stand["params"]
    RESULTS.mkdir(exist_ok=True)
    url = content_db_url(a.content_db_url)
    times = {}
    for g in a.grades:
        if a.stand_set == "reference":
            gap = stand["reference_sets"].get(str(g))
            if not gap:
                print(f"G{g}: no reference set, skipped"); continue
        elif a.stand_set == "B":
            gap = stand["stand_b"]["grades"][str(g)]["gap_l3"]
        else:
            gap = stand["grades"][str(g)]["gap_l3"]
        out = out_path(a.tag, g)
        cmd = [sys.executable, str(TOOLS / "cat_sim.py"), "--grade", str(g), "--n-students", str(a.n_students or P["n_students"]),
               "--seed", str(a.seed if a.seed is not None else P["seed"]), "--gap-fraction", str(P["gap_fraction"]), "--gap-fail-p", str(P["gap_fail_p"]),
               "--dependant-depth", str(P["dependant_depth"]), "--workers", str(a.workers),
               "--content-db-url", url, "--out", str(out), "--gap-l3", *gap]
        for kv in a.setting:
            cmd += ["--setting", kv]
        t0 = time.time()
        r = subprocess.run(cmd, cwd=str(DIAG), capture_output=True, text=True)
        dt = time.time() - t0
        if r.returncode != 0:
            print(f"G{g} FAILED:\n{(r.stderr or r.stdout)[-1500:]}"); sys.exit(1)
        d = json.load(open(out))
        d["rootcause"] = {"tag": a.tag, "grade": g, "stand_set": a.stand_set, "gap_l3": gap, "runtime_s": round(dt, 1),
                          "setting_overrides": a.setting, "n_students": a.n_students or P["n_students"],
                          "seed": a.seed if a.seed is not None else P["seed"]}
        json.dump(d, open(out, "w"), ensure_ascii=False)
        times[g] = dt
        s = d["arms"]["A"]["summary"]
        print(f"G{g} done {dt:.0f}s  acc3={s['acc_category']:.3f} cause={s['detect_cause']:.3f} named={s['detect_named']:.3f} "
              f"topic={s['gap_topic_named']:.3f}", flush=True)
    print("runtime_s:", {g: round(t) for g, t in times.items()}, "total", round(sum(times.values())))


def load_arm(tag, g):
    p = out_path(tag, g)
    if not p.exists():
        return None
    return json.load(open(p))


def fmt(v, key):
    if v is None:
        return "  n/a"
    return f"{v:.3f}" if key in ("rmse_theta",) else (f"{v:.1f}" if key == "len_mean" else f"{100 * v:.1f}")


def cmd_table(a):
    stand = json.load(open(STAND))
    rows, res = [], {}
    for g in GRADES:
        d = load_arm(a.tag, g)
        if not d:
            continue
        s = d["arms"]["A"]["summary"]
        if (d.get("rootcause") or {}).get("stand_set") == "B":
            detail = stand["stand_b"]["grades"][str(g)]["detail"]
            cls = {k: ("dependant" if v["in_grade_hard_dependants"] else "typical") for k, v in detail.items()}
        else:
            cls = {k: v["class"] for k, v in stand["grades"][str(g)]["detail"].items() if "class" in v}
        by = {}
        for c in ("typical", "dependant"):
            st = [r for r in d["arms"]["A"]["students"] if r["gap"] and cls.get(r["gap"]) == c]
            if st:
                by[c] = {m: float(np.mean([bool(r[k]) for r in st])) for m, k in
                         (("cause", "cause"), ("named", "named"), ("root", "detected"), ("conf_is_G", "confirmed_gap_is_G"),
                          ("topic_named", "gap_topic_named"), ("scan", "scan_triggered"))}
                by[c]["n"] = len(st)
        res[g] = {"summary": {k: s.get(k) for k, _ in TABLE_KEYS}, "by_class": by, "runtime_s": (d.get("rootcause") or {}).get("runtime_s"),
                  "settings": d.get("settings")}
    hdr = "G   " + " ".join(f"{l:>11s}" for _, l in TABLE_KEYS)
    print(f"[{a.tag}] values in % except RMSE, len"); print(hdr)
    for g, r in res.items():
        print(f"G{g:<3d}" + " ".join(f"{fmt(r['summary'][k], k):>11s}" for k, _ in TABLE_KEYS))
    if a.out:
        json.dump({"tag": a.tag, "grades": res}, open(a.out, "w"), ensure_ascii=False, indent=1)


def pooled(tag_grades):
    """concat students across grades with a unique index (paired between arms)"""
    out = []
    for g, d in tag_grades:
        for r in d["arms"]["A"]["students"]:
            out.append({**r, "i": g * 100000 + r["i"]})
    return out


def cmd_compare(a):
    import cat_sim
    res, rows, pair_b, pair_v = {}, [], [], []
    for g in GRADES:
        b, v = load_arm(a.base, g), load_arm(a.variant, g)
        if not (b and v):
            continue
        sb, sv = b["arms"]["A"]["students"], v["arms"]["A"]["students"]
        res[f"G{g}"] = cat_sim.paired_bootstrap(sb, sv, a.n_boot)
        pair_b.append((g, b)); pair_v.append((g, v))
    if len(pair_b) > 1:
        res["ALL"] = cat_sim.paired_bootstrap(pooled(pair_b), pooled(pair_v), a.n_boot)
    keys = [(k, l) for k, l in TABLE_KEYS if k in next(iter(res.values()))] if res else []
    lines = [f"variant '{a.variant}' vs base '{a.base}': diff (variant - base), 95% CI paired bootstrap; % points (RMSE, len absolute); * = CI excludes 0"]
    for k, l in keys:
        lines.append(f"-- {l} ({k})")
        for g, r in res.items():
            x = r[k]
            sc = 1 if k in ("rmse_theta", "len_mean") else 100
            star = "*" if (x["ci95"][0] > 0 or x["ci95"][1] < 0) else " "
            lines.append(f"  {g:>4s} base={x['A'] * sc:7.2f} var={x['B'] * sc:7.2f} d={x['diff'] * sc:+7.2f} [{x['ci95'][0] * sc:+7.2f},{x['ci95'][1] * sc:+7.2f}]{star}")
    # compact table, transposed: one row per metric, one column per grade; cell = d[lo,hi] (% points; RMSE/len absolute)
    comp = ["", "compact: d[95% CI], * = CI excludes 0"]
    comp.append(f"{'metric':12s}" + "".join(f"{g:>20s}" for g in res))
    for k, l in keys:
        sc = 1 if k in ("rmse_theta", "len_mean") else 100
        cells = []
        for g, r in res.items():
            x = r[k]
            cells.append(f"{x['diff'] * sc:+.1f}[{x['ci95'][0] * sc:+.1f},{x['ci95'][1] * sc:+.1f}]"
                         + ("*" if (x["ci95"][0] > 0 or x["ci95"][1] < 0) else ""))
        comp.append(f"{l:12s}" + "".join(f"{c:>20s}" for c in cells))
    text = "\n".join(lines[:1] + comp[1:] )
    print(text)
    if a.out:
        json.dump({"base": a.base, "variant": a.variant, "paired_variant_minus_base": res}, open(a.out, "w"), ensure_ascii=False, indent=1)
        Path(a.out).with_suffix(".txt").write_text("\n".join(lines) + "\n" + "\n".join(comp) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("--tag", required=True)
    r.add_argument("--setting", action="append", default=[], help="KEY=VAL override passed to cat_sim --setting")
    r.add_argument("--grades", type=int, nargs="*", default=GRADES)
    r.add_argument("--stand-set", choices=["stand", "reference", "B"], default="stand")
    r.add_argument("--n-students", type=int, default=None); r.add_argument("--seed", type=int, default=None, help="student seed (default: the stand's)")
    r.add_argument("--workers", type=int, default=8)
    r.add_argument("--content-db-url")
    t = sp.add_parser("table"); t.add_argument("--tag", required=True); t.add_argument("--out")
    c = sp.add_parser("compare"); c.add_argument("--base", required=True); c.add_argument("--variant", required=True)
    c.add_argument("--n-boot", type=int, default=2000); c.add_argument("--out")
    a = ap.parse_args()
    {"run": cmd_run, "table": cmd_table, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    main()
