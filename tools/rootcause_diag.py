#!/usr/bin/env python
"""Root-cause study, stage 3a: diagnostic metrics of ONE arm (the instrumented runs of cat_sim / rootcause_run).

  python tools/rootcause_diag.py --tag A0 --stage stage3a [--n-boot 2000]

Reads tools/sim_results/rootcause_<tag>_G<n>.json and writes tools/sim_results/rootcause_<stage>_diag.json + .txt
(summary files; the per-grade result JSONs stay gitignored).

Populations.  Gap students = those with an injected gap L3 G; "signal" L3 = G and its direct in-grade dependants (the L3s
gap students fail with p=fail_p); every other failed L3 - and every failed L3 of a gap-free student - is "noise".
theta terciles = fixed standard-normal cut points of the TRUE theta (+-0.4307: T1 weak, T2 middle, T3 strong).

Metrics (rates are shares of students unless stated):
  scan_gap / scan_nogap        a Deep Scan served >=1 item                       (existing scan_triggered)
  chain_precision              chains whose root L3 == G / all chains, gap students
  p_chain, chains_per_student  gap and gap-free students (gap-free: every chain is noise)
  conf_G, topic_G              confirmed_gap_is_G / gap_topic_named of gap students; "base" = the same event for the SAME
                               L3 list on gap-free students (matched to each gap student's G, within the scope),
                               lift = rate / base
  entries                      report entries per session (weak topics + critical topics + their detail skills)
  funnel (gap students)        V visited a signal L3 -> F failed one -> S a scan started from a failed signal L3 ->
                               R G reached (G was the origin or a probed step) in such a scan -> C confirmed_gap_is_G;
                               Rany / Q: G reached / in the initial queue of ANY scan; Fimp: failed signal L3 with
                               importance >= threshold; Fbud: ... that found the session budget already spent
  shadow rules (per failed, decided, non-final L3 visit; rule applied to the L3 visit independent of the budget):
     cur = importance >= threshold and a failing skill (current rule), act = the scan really started (budget respected),
     d1 = >=2 wrong in the L3 (or 1 wrong when the L3 has a single L4), d2 = sum(p_hat - x) >= 1.0,
     d1g / d2g = d1 / d2 AND importance >= threshold.
     P(trigger | signal L3 failed) vs P(trigger | noise L3 failed) and their ratio; student level: P(any trigger).

Confidence intervals: per grade = student bootstrap (gap and gap-free students resampled separately within the grade, as in
cat_sim.paired_bootstrap); ALL grades = cluster bootstrap by gap L3 (per grade, the gap L3 clusters are redrawn with
replacement and carry all their gap students; gap-free students are resampled within the grade); 95% percentile CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from rootcause_run import GRADES, RESULTS, content_db_url  # noqa: E402

T_CUT = NormalDist().inv_cdf(2 / 3)          # |theta| cut of the terciles of N(0,1): +-0.4307
RULES = ("cur", "act", "d1", "d2", "d1g", "d2g")
RULE_LABEL = {"cur": "current (imp>=8 & failing)", "act": "actual (budget respected)", "d1": "D1 (>=2 wrong | single L4)",
              "d2": "D2 (resid>=1.0)", "d1g": "D1 & imp>=8", "d2g": "D2 & imp>=8"}


# ─────────────────────────────────────────────────────────────────────────────
# per-student arrays
# ─────────────────────────────────────────────────────────────────────────────
def load_tag(tag, results=RESULTS):
    out = {}
    for g in GRADES:
        p = Path(results) / f"rootcause_{tag}_G{g}.json"
        if p.exists():
            out[g] = json.load(open(p))
    return out


def gap_parents(gaps):
    """L2 parent of every gap L3 (read-only content DB)."""
    from sqlalchemy import create_engine, text
    eng = create_engine(content_db_url(None))
    with eng.connect() as c:
        rows = c.execute(text("select id, parent_id from knowledge_hierarchy where id = any(:ids)"),
                         {"ids": sorted(gaps)}).all()
    eng.dispose()
    return {r[0]: r[1] for r in rows}


def build_arrays(data, l2_of=None):
    """data: grade -> loaded result file.  Returns dict of numpy arrays (one entry per student) + the cluster table."""
    recs, cols = [], []                                # cols: (grade, G) clusters in a fixed order
    for g, d in sorted(data.items()):
        gl = d["rootcause"]["gap_l3"]
        cols += [(g, G) for G in gl]
        for r in d["arms"]["A"]["students"]:
            recs.append((g, r))
    col_ix = {c: j for j, c in enumerate(cols)}
    l2_of = l2_of or gap_parents({G for _, G in cols})
    N, J = len(recs), len(cols)
    f = lambda: np.zeros(N)
    A = {k: f() for k in (
        "grade", "gap", "theta", "terc", "cluster", "scan", "ds_items", "nch", "chG", "conf", "topic", "entries", "wt", "ct",
        "dt", "V", "F", "S", "R", "Rany", "Rorig", "Rprobe", "Cprobe", "Q", "Fimp", "Fbud", "C", "budget_sig", "n_sig_scans", "budget_noise", "n_noise_scans",
        "sig_n", "noise_n", "n_cut", "n_terminal", "n_visits", "n_failed")}
    for rule in RULES:
        A[f"sig_{rule}"], A[f"noise_{rule}"], A[f"any_{rule}"], A[f"anysig_{rule}"] = f(), f(), f(), f()
    A["cluster"][:] = -1
    IC, IT = np.zeros((N, J)), np.zeros((N, J))        # would-be conf / topic indicators for each cluster's L3 (grade-matched)
    aux = {}
    for i, (g, r) in enumerate(recs):
        G = r["gap"]
        A["grade"][i], A["gap"][i], A["theta"][i] = g, 1.0 if G else 0.0, r["theta"]
        A["terc"][i] = 0 if r["theta"] < -T_CUT else (2 if r["theta"] >= T_CUT else 1)
        A["scan"][i], A["ds_items"][i] = float(bool(r.get("scan_triggered"))), r["ds_items"]
        roots = r.get("chain_roots") or []
        A["nch"][i] = r["n_chains"]
        A["chG"][i] = sum(1 for x in roots if G and x == G)
        A["entries"][i], A["wt"][i], A["ct"][i], A["dt"][i] = (r["weak_entries"], r["n_weak_topics"], r["n_crit_topics"],
                                                               r["n_detail_skills"])
        conf = set(r.get("confirmed_l3s") or [])
        named = set(r.get("named_l2s") or [])
        for j, (gg, GG) in enumerate(cols):
            if gg == g:
                IC[i, j] = GG in conf
                IT[i, j] = l2_of.get(GG) in named
        if G:
            A["cluster"][i] = col_ix[(g, G)]
            A["conf"][i], A["topic"][i] = float(bool(r.get("confirmed_gap_is_G"))), float(bool(r.get("gap_topic_named")))
            vis = [v for v in r["l3_visits"] if v.get("complete")]
            sc = r["scan_log"]
            A["V"][i] = any(v["sig"] for v in vis)
            A["F"][i] = any(v["sig"] and v["failed"] for v in vis)
            A["S"][i] = any(s["origin_sig"] for s in sc)
            A["R"][i] = any(s["origin_sig"] and (s["G_origin"] or s["G_probed"]) for s in sc)
            A["Rany"][i] = any(s["G_origin"] or s["G_probed"] for s in sc)
            A["Rorig"][i] = any(s["G_origin"] for s in sc)                      # the failed L3 was G itself
            A["Rprobe"][i] = any(s["G_probed"] and not s["G_origin"] for s in sc)  # G probed as a prerequisite
            A["Cprobe"][i] = any(s["G_confirmed"] and not s["G_origin"] for s in sc)
            A["Q"][i] = any(s["G_in_queue"] for s in sc)
            A["C"][i] = A["conf"][i]
            shd = [s for s in r["shadow_triggers"] if s["sig"]]
            A["Fimp"][i] = any(s["imp_ok"] for s in shd)
            A["Fbud"][i] = any(s["cur"] and s["budget_spent"] for s in shd)
        for s in r["scan_log"]:
            k = "sig" if s["origin_sig"] else "noise"
            A[f"budget_{k}"][i] += s["budget_used"]
            A[f"n_{k}_scans"][i] += 1
        A["n_visits"][i] = sum(1 for v in r["l3_visits"] if v.get("complete"))
        A["n_cut"][i] = sum(1 for v in r["l3_visits"] if not v.get("complete"))
        A["n_terminal"][i] = sum(1 for v in r["l3_visits"] if v.get("complete") and v.get("terminal"))
        for k, v in (r.get("trace_aux") or {}).items():
            aux[k] = aux.get(k, 0) + v
        for s in r["shadow_triggers"]:
            if s["terminal"]:
                continue                               # the service may not have decided this L3 (session over)
            A["n_failed"][i] += 1
            side = "sig" if s["sig"] else "noise"
            A[f"{side}_n"][i] += 1
            flags = {"cur": s["cur"], "act": bool(s["actual"]), "d1": s["d1"], "d2": s["d2"],
                     "d1g": s["d1"] and s["imp_ok"], "d2g": s["d2"] and s["imp_ok"]}
            for rule, on in flags.items():
                A[f"{side}_{rule}"][i] += float(on)
                A[f"any_{rule}"][i] = max(A[f"any_{rule}"][i], float(on))
                if s["sig"]:
                    A[f"anysig_{rule}"][i] = max(A[f"anysig_{rule}"][i], float(on))
    A["gapb"] = A["gap"] > 0
    A["IC"], A["IT"] = IC, IT
    return A, cols, aux


# ─────────────────────────────────────────────────────────────────────────────
# resampling weights
# ─────────────────────────────────────────────────────────────────────────────
def student_weights(A, B, rng):
    """B x N multiplicities: gap and gap-free students resampled separately within each grade."""
    N = len(A["grade"])
    W = np.zeros((B, N), np.float32)
    for g in np.unique(A["grade"]):
        for flag in (True, False):
            idx = np.flatnonzero((A["grade"] == g) & (A["gapb"] == flag))
            if not len(idx):
                continue
            draw = rng.integers(0, len(idx), (B, len(idx)))
            flat = (np.arange(B)[:, None] * len(idx) + draw).ravel()
            W[:, idx] = np.bincount(flat, minlength=B * len(idx)).reshape(B, len(idx))
    return W


def cluster_weights(A, cols, B, rng):
    """B x N multiplicities: per grade the gap-L3 clusters are redrawn with replacement (gap students stay together in
    their cluster); gap-free students are resampled within the grade."""
    N = len(A["grade"])
    W = np.zeros((B, N), np.float32)
    for g in np.unique(A["grade"]):
        js = [j for j, (gg, _) in enumerate(cols) if gg == g]
        draw = rng.integers(0, len(js), (B, len(js)))
        flat = (np.arange(B)[:, None] * len(js) + draw).ravel()
        mult = np.bincount(flat, minlength=B * len(js)).reshape(B, len(js))
        for k, j in enumerate(js):
            idx = np.flatnonzero(A["cluster"] == j)
            if len(idx):
                W[:, idx] = mult[:, k:k + 1]
        idx = np.flatnonzero((A["grade"] == g) & ~A["gapb"])
        if len(idx):
            d2 = rng.integers(0, len(idx), (B, len(idx)))
            fl = (np.arange(B)[:, None] * len(idx) + d2).ravel()
            W[:, idx] = np.bincount(fl, minlength=B * len(idx)).reshape(B, len(idx))
    return W


# ─────────────────────────────────────────────────────────────────────────────
# metrics
# ─────────────────────────────────────────────────────────────────────────────
def _div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, a / np.where(b > 0, b, 1), np.nan)


def metrics(A, cols, W, scope):
    """All metrics for the students in `scope` (bool mask), weights W (rows = replicates)."""
    gap, ng = scope & A["gapb"], scope & ~A["gapb"]
    s = lambda v, m: W @ (np.asarray(v, np.float32) * m)                 # weighted sum per replicate
    mean = lambda name, m: _div(s(A[name], m), s(np.ones(len(m)), m))
    out = {"n_gap": s(np.ones(len(gap)), gap), "n_nogap": s(np.ones(len(ng)), ng)}
    for name, key in (("scan", "scan"), ("ds_items", "ds_items"), ("p_chain", None), ("chains_ps", "nch"),
                      ("entries", "entries"), ("weak_topics", "wt"), ("crit_topics", "ct"), ("detail_skills", "dt")):
        for side, m in (("gap", gap), ("nogap", ng)):
            if key is None:
                out[f"{name}_{side}"] = _div(s(A["nch"] > 0, m), s(np.ones(len(m)), m))
            else:
                out[f"{name}_{side}"] = mean(key, m)
    out["chain_precision"] = _div(s(A["chG"], gap), s(A["nch"], gap))
    out["n_chains_gap"] = s(A["nch"], gap)
    # lift over the matched gap-free base rate
    cl = A["cluster"].astype(int)
    colg = np.array([g for g, _ in cols])
    Gm = np.zeros((len(cl), len(cols)), np.float32)
    Gm[np.flatnonzero(cl >= 0), cl[cl >= 0]] = 1.0
    Gm *= gap[:, None]
    NG = (ng[:, None] & (A["grade"][:, None] == colg[None, :])).astype(np.float32)
    n_g = W @ Gm                                                           # gap students per cluster
    den = np.maximum(W @ NG, 1e-9)
    for name, ind, rate in (("conf", A["IC"], A["conf"]), ("topic", A["IT"], A["topic"])):
        base_j = (W @ (ind.astype(np.float32) * NG)) / den                 # P(event for L3 j | gap-free), per cluster
        matched = (n_g * base_j).sum(1)
        pos = s(rate, gap)
        tot = n_g.sum(1)
        out[f"{name}_gap"] = _div(pos, tot)
        out[f"{name}_base"] = _div(matched, tot)
        out[f"{name}_lift"] = _div(pos, matched)
        out[f"{name}_diff"] = out[f"{name}_gap"] - out[f"{name}_base"]
    # funnel (gap students)
    for k in ("V", "F", "S", "R", "Rany", "Rorig", "Rprobe", "Cprobe", "Q", "C", "Fimp", "Fbud"):
        out[f"f_{k}"] = _div(s(A[k], gap), s(np.ones(len(gap)), gap))
    # budget at the start of a scan
    for k in ("sig", "noise"):
        out[f"budget_start_{k}"] = _div(s(A[f"budget_{k}"], scope), s(A[f"n_{k}_scans"], scope))
    # shadow rules
    sig_n, noise_n = s(A["sig_n"], scope), s(A["noise_n"], scope)
    for rule in RULES:
        ps = _div(s(A[f"sig_{rule}"], scope), sig_n)
        pn = _div(s(A[f"noise_{rule}"], scope), noise_n)
        out[f"sh_sig_{rule}"], out[f"sh_noise_{rule}"], out[f"sh_ratio_{rule}"] = ps, pn, _div(ps, pn)
        ag, an = mean(f"any_{rule}", gap), mean(f"any_{rule}", ng)
        out[f"any_gap_{rule}"], out[f"any_nogap_{rule}"], out[f"any_ratio_{rule}"] = ag, an, _div(ag, an)
    out["sig_failed_per_gap_student"] = _div(s(A["sig_n"], gap), s(np.ones(len(gap)), gap))
    out["noise_failed_per_student"] = _div(s(A["noise_n"], scope), s(np.ones(len(scope)), scope))
    return out


def ci(x):
    x = x[np.isfinite(x)]
    return [float(v) for v in np.percentile(x, [2.5, 97.5])] if len(x) > 20 else [None, None]


def evaluate(A, cols, scope, w_boot, w_ones):
    pt = metrics(A, cols, w_ones, scope)
    bt = metrics(A, cols, w_boot, scope)
    return {k: {"v": float(pt[k][0]) if np.isfinite(pt[k][0]) else None, "ci95": ci(bt[k])} for k in pt}


# ─────────────────────────────────────────────────────────────────────────────
# report
# ─────────────────────────────────────────────────────────────────────────────
def fv(x, p=3, pct=False):
    if x is None or x.get("v") is None:
        return "n/a"
    v = x["v"] * (100 if pct else 1)
    return f"{v:.{p}f}"


def fci(x, p=3, pct=False, ci_on=True):
    if x is None or x.get("v") is None:
        return "n/a"
    s = fv(x, p, pct)
    if not ci_on or x["ci95"][0] is None:
        return s
    k = 100 if pct else 1
    return f"{s}[{x['ci95'][0] * k:.{p}f},{x['ci95'][1] * k:.{p}f}]"


def table(title, rows, cols, width=21):
    lines = ["", title, f"{'metric':32s}" + "".join(f"{c:>{width}s}" for c in cols)]
    for label, cells in rows:
        lines.append(f"{label:32s}" + "".join(f"{c:>{width}s}" for c in cells))
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--stage", default="stage3a")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--results", type=Path, default=RESULTS)
    a = ap.parse_args()
    data = load_tag(a.tag, a.results)
    if not data:
        raise SystemExit(f"no result files for tag {a.tag}")
    A, cols, aux = build_arrays(data)
    N = len(A["grade"])
    rng = np.random.default_rng(a.seed)
    w1 = np.ones((1, N), np.float32)
    w_stu = student_weights(A, a.n_boot, rng)
    w_clu = cluster_weights(A, cols, a.n_boot, rng)
    grades = sorted(data)
    allm = np.ones(N, bool)
    res = {"ALL": evaluate(A, cols, allm, w_clu, w1)}
    for g in grades:
        res[f"G{g}"] = evaluate(A, cols, A["grade"] == g, w_stu, w1)
    for t, name in enumerate(("T1", "T2", "T3")):
        res[f"ALL_{name}"] = evaluate(A, cols, A["terc"] == t, w_clu, w1)
        for g in grades:                                  # per grade x tercile: point estimates only
            sc = (A["grade"] == g) & (A["terc"] == t)
            res[f"G{g}_{name}"] = {k: {"v": v["v"], "ci95": [None, None]} for k, v in
                                    evaluate(A, cols, sc, w_stu[:50], w1).items()}
    heads = ["ALL"] + [f"G{g}" for g in grades]
    L = [f"{a.stage}: tag {a.tag}, grades {grades}, N={N} students ({int(A['gap'].sum())} with gap), n_boot={a.n_boot}",
         "ALL = 95% CI by cluster bootstrap over gap L3 (clusters redrawn per grade); G<n> = 95% CI by student bootstrap.",
         f"theta terciles (true theta): T1 < {-T_CUT:.3f} <= T2 < {T_CUT:.3f} <= T3",
         "instrumentation self-checks (all should be 0 except terminal/cut): " + json.dumps(aux)]
    pct = lambda k, **kw: (lambda sc: fci(res[sc][k], 1, True, **kw))
    num = lambda k, p=3, **kw: (lambda sc: fci(res[sc][k], p, False, **kw))

    def row(label, fn):
        return label, [fn(sc) for sc in heads]

    L += table("1. scan, chains, report (% of students unless stated)", [
        row("n gap / no gap", lambda sc: f"{res[sc]['n_gap']['v']:.0f}/{res[sc]['n_nogap']['v']:.0f}"),
        row("scan rate, gap", pct("scan_gap")), row("scan rate, no gap", pct("scan_nogap")),
        row("Deep Scan items/student, gap", num("ds_items_gap", 2)), row("Deep Scan items/student, no gap", num("ds_items_nogap", 2)),
        row("chain_precision (root==G)", pct("chain_precision")),
        row("chains total, gap", lambda sc: f"{res[sc]['n_chains_gap']['v']:.0f}"),
        row("P(any chain), gap", pct("p_chain_gap")), row("chains/student, gap", num("chains_ps_gap", 2)),
        row("P(any chain), no gap", pct("p_chain_nogap")), row("chains/student, no gap", num("chains_ps_nogap", 2)),
        row("confirmed_gap_is_G, gap", pct("conf_gap")), row("  base (gap-free, same L3 list)", pct("conf_base")),
        row("  lift (x)", num("conf_lift", 2)), row("  diff (pp)", pct("conf_diff")),
        row("gap_topic_named, gap", pct("topic_gap")), row("  base (gap-free)", pct("topic_base")),
        row("  lift (x)", num("topic_lift", 2)), row("  diff (pp)", pct("topic_diff")),
        row("report entries, gap", num("entries_gap", 2)), row("report entries, no gap", num("entries_nogap", 2)),
        row("  weak topics gap / no gap", lambda sc: f"{fv(res[sc]['weak_topics_gap'], 2)}/{fv(res[sc]['weak_topics_nogap'], 2)}"),
        row("  critical topics gap / no gap", lambda sc: f"{fv(res[sc]['crit_topics_gap'], 2)}/{fv(res[sc]['crit_topics_nogap'], 2)}"),
        row("  detail skills gap / no gap", lambda sc: f"{fv(res[sc]['detail_skills_gap'], 2)}/{fv(res[sc]['detail_skills_nogap'], 2)}"),
    ], heads)

    rows = []
    for name in ("T1", "T2", "T3"):
        for label, key, kind in (("P(any chain), no gap", "p_chain_nogap", "pct"), ("chains/student, no gap", "chains_ps_nogap", "n2"),
                                 ("scan rate, no gap", "scan_nogap", "pct"), ("scan rate, gap", "scan_gap", "pct"),
                                 ("chain_precision, gap", "chain_precision", "pct"), ("conf_G lift (x), gap", "conf_lift", "n2"),
                                 ("topic_G lift (x), gap", "topic_lift", "n2"), ("report entries, no gap", "entries_nogap", "n2"),
                                 ("report entries, gap", "entries_gap", "n2")):
            f_ = (lambda sc, key=key, kind=kind, name=name: fci(res[f"{sc}_{name}"][key], 1, True, ci_on=(sc == "ALL"))
                  if kind == "pct" else fci(res[f"{sc}_{name}"][key], 2, False, ci_on=(sc == "ALL")))
            rows.append((f"{name} {label}", [f_(sc) for sc in heads]))
    L += table("2. by true-theta tercile (ALL with cluster-bootstrap CI, grades: point estimates)", rows, heads)

    L += table("3. funnel, share of gap students (V>=F>=S>=R nested; C and Rany/Q count ANY scan, a noise-origin scan can descend to G)", [
        row("V visited a signal L3", pct("f_V")), row("F failed a signal L3", pct("f_F")),
        row("  Fimp: ...with importance>=8", pct("f_Fimp")), row("  Fbud: ...found the budget spent", pct("f_Fbud")),
        row("S scan started from it", pct("f_S")), row("R G reached in such a scan", pct("f_R")),
        row("C confirmed_gap_is_G", pct("f_C")), row("Rany G reached, any scan", pct("f_Rany")),
        row("  Rorig: the failed L3 was G itself", pct("f_Rorig")), row("  Rprobe: G probed as prerequisite", pct("f_Rprobe")),
        row("  Cprobe: G confirmed by a probe", pct("f_Cprobe")),
        row("Q G in initial queue, any scan", pct("f_Q")),
        row("S|F  (share of F)", lambda sc: f"{_r(res[sc], 'f_S', 'f_F'):.1f}"),
        row("R|S", lambda sc: f"{_r(res[sc], 'f_R', 'f_S'):.1f}"), row("C|Rany", lambda sc: f"{_r(res[sc], 'f_C', 'f_Rany'):.1f}"),
        row("budget used at scan start: sig/noise", lambda sc: f"{fv(res[sc]['budget_start_sig'], 2)}/{fv(res[sc]['budget_start_noise'], 2)}"),
    ], heads)

    rows = []
    for rule in RULES:
        rows.append((f"{rule:3s} P(trig|signal failed)", [fci(res[sc][f"sh_sig_{rule}"], 1, True, ci_on=(sc == "ALL")) for sc in heads]))
        rows.append((f"{rule:3s} P(trig|noise failed)", [fci(res[sc][f"sh_noise_{rule}"], 1, True, ci_on=(sc == "ALL")) for sc in heads]))
        rows.append((f"{rule:3s} ratio signal/noise", [fci(res[sc][f"sh_ratio_{rule}"], 2, False, ci_on=(sc == "ALL")) for sc in heads]))
    L += table("4. shadow trigger rules, per failed decided L3 visit (" + "; ".join(f"{k}={v}" for k, v in RULE_LABEL.items()) + ")", rows, heads)
    rows = []
    for rule in RULES:
        rows.append((f"{rule:3s} P(any trig) gap", [fci(res[sc][f"any_gap_{rule}"], 1, True, ci_on=(sc == "ALL")) for sc in heads]))
        rows.append((f"{rule:3s} P(any trig) no gap", [fci(res[sc][f"any_nogap_{rule}"], 1, True, ci_on=(sc == "ALL")) for sc in heads]))
        rows.append((f"{rule:3s} ratio gap/no gap", [fci(res[sc][f"any_ratio_{rule}"], 2, False, ci_on=(sc == "ALL")) for sc in heads]))
    rows.append(("failed signal L3/gap student", [fci(res[sc]["sig_failed_per_gap_student"], 2, False, ci_on=(sc == "ALL")) for sc in heads]))
    rows.append(("failed L3/student (noise)", [fci(res[sc]["noise_failed_per_student"], 2, False, ci_on=(sc == "ALL")) for sc in heads]))
    L += table("5. shadow rules, student level: P(student has >=1 triggering failed L3), ignoring the budget", rows, heads)
    rows = []
    for rule in RULES:
        for name in ("T1", "T2", "T3"):
            rows.append((f"{rule:3s} {name} P(any trig) no gap", [fci(res[f"{sc}_{name}"][f"any_nogap_{rule}"], 1, True, ci_on=(sc == "ALL")) for sc in heads]))
    L += table("6. shadow rules, gap-free students by theta tercile: P(any trigger)", rows, heads)

    text = "\n".join(L) + "\n"
    out_json = a.results / f"rootcause_{a.stage}_diag.json"
    json.dump({"tag": a.tag, "n_boot": a.n_boot, "grades": grades, "n_students": N, "instrumentation_aux": aux,
               "theta_tercile_cut": T_CUT, "results": res}, open(out_json, "w"), ensure_ascii=False, indent=1)
    out_json.with_suffix(".txt").write_text(text)
    print(text)


def _r(r, num, den):
    a, b = r[num]["v"], r[den]["v"]
    return 100 * a / b if (a is not None and b) else float("nan")


if __name__ == "__main__":
    main()
