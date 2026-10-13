#!/usr/bin/env python
"""Root-cause study, stage 3a: diagnostic metrics of ONE arm (the instrumented runs of cat_sim / rootcause_run).

  python tools/rootcause_diag.py --tag A0 --stage stage3a [--n-boot 2000]                 # one arm (stage 3a tables)
  python tools/rootcause_diag.py --base A0 --variants A1 A2 A3 A4 A5 --stage stage3b       # arms vs base + acceptance verdicts
  python tools/rootcause_diag.py --consistency A3 A5                                       # finalists: stand A vs B vs seed 2

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

Compare mode (stage 3b/3c): every metric of the variant minus the base on the SAME students (same weights in the same
replicate, so the difference is paired), scopes ALL / theta tercile / grade / gap-L3 class (eligible, non_eligible, typical);
the acceptance criteria of tools/rootcause_accept.json (primary: effect AND a CI beyond 0; guardrails: non-inferiority
margins on the 95% CI; secondary: reported; ADVANCE = every primary and every guardrail) are evaluated on the ALL-grades cluster-bootstrap CIs and written into the .txt/.json.

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
from rootcause_run import GRADES, RESULTS, STAND, content_db_url  # noqa: E402

T_CUT = NormalDist().inv_cdf(2 / 3)          # |theta| cut of the terciles of N(0,1): +-0.4307
RULES = ("cur", "act", "d1", "d2", "d1g", "d2g")
RULE_LABEL = {"cur": "current (imp>=8 & failing)", "act": "actual (budget respected)", "d1": "D1 (>=2 wrong | single L4)",
              "d2": "D2 (resid>=1.0)", "d1g": "D1 & imp>=8", "d2g": "D2 & imp>=8"}


# ─────────────────────────────────────────────────────────────────────────────
# per-student arrays
# ─────────────────────────────────────────────────────────────────────────────
CLASSES = ("eligible", "non_eligible", "typical")      # a trigger-relevant view of the gap L3: see gap_class()


def gap_class(stand, stand_set, grade, G):
    """eligible = a direct in-grade dependant with importance >= 8 exists (a failed dependant can start a scan that reaches G);
    non_eligible = dependants exist, all < 8; typical = no dependant.  Stand A: the class/trigger_eligible fields of its detail;
    stand B: its class labels (eligible_fill counts as eligible)."""
    if stand_set == "B":
        c = stand["stand_b"]["grades"][str(grade)]["detail"][G]["class"]
        return "eligible" if c.startswith("eligible") else c
    d = stand["grades"][str(grade)]["detail"][G]
    return "typical" if d["class"] == "typical" else ("eligible" if d["trigger_eligible"] else "non_eligible")

def load_tag(tag, results=RESULTS):
    out = {}
    for g in GRADES:
        p = Path(results) / f"rootcause_{tag}_G{g}.json"
        if p.exists():
            out[g] = json.load(open(p))
    return out


def hierarchy():
    """L3 -> L2 and L2 -> L1 parents (read-only content DB): topics / sections measured per session."""
    from sqlalchemy import create_engine, text
    eng = create_engine(content_db_url(None))
    with eng.connect() as c:
        rows = c.execute(text("select id, level, parent_id from knowledge_hierarchy where level in ('L2','L3')")).all()
    eng.dispose()
    l2 = {r[0]: r[2] for r in rows if r[1] == "L3"}
    l1 = {r[0]: r[2] for r in rows if r[1] == "L2"}
    return l2, l1


def build_arrays(data, l2_of=None, hier=None):
    """data: grade -> loaded result file.  Returns dict of numpy arrays (one entry per student) + the cluster table."""
    recs, cols = [], []                                # cols: (grade, G) clusters in a fixed order
    for g, d in sorted(data.items()):
        gl = d["rootcause"]["gap_l3"]
        cols += [(g, G) for G in gl]
        for r in d["arms"]["A"]["students"]:
            recs.append((g, r))
    col_ix = {c: j for j, c in enumerate(cols)}
    hier = hier or hierarchy()
    l2_of = l2_of or {G: hier[0].get(G) for _, G in cols}
    N, J = len(recs), len(cols)
    f = lambda: np.zeros(N)
    A = {k: f() for k in (
        "grade", "gap", "theta", "terc", "cluster", "scan", "ds_items", "nch", "chG", "conf", "topic", "entries", "wt", "ct",
        "dt", "V", "F", "S", "R", "Rany", "Rorig", "Rprobe", "Cprobe", "Q", "Fimp", "Fbud", "C", "budget_sig", "n_sig_scans", "budget_noise", "n_noise_scans",
        "sig_n", "noise_n", "n_cut", "n_terminal", "n_visits", "n_failed",
        "acc", "sq", "items", "maxit", "cause", "detected", "named", "fp", "cls", "topics", "sections", "l3n")}
    for rule in RULES:
        A[f"sig_{rule}"], A[f"noise_{rule}"], A[f"any_{rule}"], A[f"anysig_{rule}"] = f(), f(), f(), f()
    A["cluster"][:] = -1
    A["cls"][:] = -1
    stand = json.loads(STAND.read_text())
    stand_sets = {g: d["rootcause"].get("stand_set", "stand") for g, d in data.items()}
    A["items_oh"] = np.zeros((N, 64), np.float32)
    IC, IT = np.zeros((N, J)), np.zeros((N, J))        # would-be conf / topic indicators for each cluster's L3 (grade-matched)
    aux = {}
    for i, (g, r) in enumerate(recs):
        G = r["gap"]
        A["grade"][i], A["gap"][i], A["theta"][i] = g, 1.0 if G else 0.0, r["theta"]
        A["terc"][i] = 0 if r["theta"] < -T_CUT else (2 if r["theta"] >= T_CUT else 1)
        A["scan"][i], A["ds_items"][i] = float(bool(r.get("scan_triggered"))), r["ds_items"]
        A["acc"][i], A["sq"][i] = float(r["cat_true"] == r["cat_hat"]), (r["theta_hat"] - r["theta"]) ** 2
        A["items"][i], A["maxit"][i] = r["items"], float(bool(r.get("hit_max_items")))
        vis_l3 = {v["l3"] for v in r["l3_visits"] if v.get("n_items")}          # navigation L3s measured (warm-up is identical in all arms)
        vis_l2 = {hier[0].get(x) for x in vis_l3} - {None}
        A["l3n"][i], A["topics"][i] = len(vis_l3), len(vis_l2)
        A["sections"][i] = len({hier[1].get(x) for x in vis_l2} - {None})
        A["items_oh"][i, min(int(r["items"]), 63)] = 1.0
        A["cause"][i], A["detected"][i], A["named"][i], A["fp"][i] = (float(bool(r["cause"])), float(bool(r["detected"])),
                                                                     float(bool(r["named"])), float(bool(r["fp"])))
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
            A["cls"][i] = CLASSES.index(gap_class(stand, stand_sets[g], g, G))
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
    # level estimation, length (all students of the scope), root-cause detection (gap) and false claims (gap-free)
    out["acc_category"] = mean("acc", scope)
    out["rmse_theta"] = np.sqrt(mean("sq", scope))
    out["len_mean"] = mean("items", scope)
    out["hit_max_items"] = mean("maxit", scope)
    counts = W @ (A["items_oh"] * scope[:, None])                          # replicates x item-count histogram
    cum = np.cumsum(counts, axis=1)
    out["len_p90"] = (cum >= 0.9 * cum[:, -1:]).argmax(axis=1).astype(float)
    for name, key in (("detect_cause", "cause"), ("detect_root", "detected"), ("detect_named", "named")):
        out[name] = mean(key, gap)
    out["fp_nogap"] = mean("fp", ng)
    out["signal_cause"] = out["detect_cause"] - out["fp_nogap"]
    out["signal_root"] = out["detect_root"] - out["fp_nogap"]
    out["topics_measured"] = mean("topics", scope)                       # distinct L2 topics with a navigation visit
    out["sections_measured"] = mean("sections", scope)
    out["l3_measured"] = mean("l3n", scope)
    out["scan_signal"] = out["scan_gap"] - out["scan_nogap"]
    out["chains_ps_signal"] = out["chains_ps_gap"] - out["chains_ps_nogap"]
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
    ap.add_argument("--tag", help="one-arm tables for this arm (stage 3a)")
    ap.add_argument("--base", help="compare mode: the base arm")
    ap.add_argument("--variants", nargs="+", help="compare mode: arms to compare with --base")
    ap.add_argument("--accept", type=Path, default=ACCEPT)
    ap.add_argument("--consistency", nargs="+", metavar="ARM", help="finalists: check stand A / stand B seed 1 / seed 2 agree")
    ap.add_argument("--stages", nargs="+", default=["stage3b", "stage3c_s1", "stage3c_s2"], help="compare stages read by --consistency")
    ap.add_argument("--stage", default="stage3a")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--results", type=Path, default=RESULTS)
    a = ap.parse_args()
    if a.consistency:
        return consistency_main(a)
    if a.variants:
        if not a.base:
            ap.error("--variants needs --base")
        return compare_main(a)
    if not a.tag:
        ap.error("--tag (one arm) or --base with --variants (compare) is required")
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


# ─────────────────────────────────────────────────────────────────────────────
# compare mode: variants minus base, acceptance criteria
# ─────────────────────────────────────────────────────────────────────────────
ACCEPT = TOOLS / "rootcause_accept.json"
# (metric, label, scale, decimals) of the compact comparison tables
COMPARE_ROWS = [
    ("acc_category", "acc3 (pp)", 100, 1), ("rmse_theta", "RMSE", 1, 3), ("len_mean", "len", 1, 2), ("len_p90", "p90", 1, 1),
    ("hit_max_items", "max_items (pp)", 100, 1), ("ds_items_gap", "ds items gap", 1, 2), ("ds_items_nogap", "ds items no gap", 1, 2),
    ("scan_gap", "scan gap (pp)", 100, 1), ("scan_nogap", "scan no gap (pp)", 100, 1), ("scan_signal", "scan gap-nogap (pp)", 100, 1),
    ("chain_precision", "chain_precision (pp)", 100, 1), ("p_chain_nogap", "P(chain) no gap (pp)", 100, 1),
    ("chains_ps_nogap", "chains/stud no gap", 1, 2), ("p_chain_gap", "P(chain) gap (pp)", 100, 1),
    ("conf_gap", "conf_is_G gap (pp)", 100, 1), ("conf_diff", "  over base (pp)", 100, 1), ("topic_gap", "topic_named gap (pp)", 100, 1),
    ("detect_cause", "cause (pp)", 100, 1), ("detect_root", "root (pp)", 100, 1), ("fp_nogap", "fp no gap (pp)", 100, 1),
    ("signal_cause", "sig_c = cause-fp (pp)", 100, 1), ("signal_root", "sig_r = root-fp (pp)", 100, 1),
    ("conf_lift", "conf_is_G lift (x)", 1, 2), ("topics_measured", "topics measured", 1, 2), ("sections_measured", "sections measured", 1, 2),
    ("f_S", "funnel S (pp)", 100, 1), ("f_R", "funnel R (pp)", 100, 1),
    ("f_C", "funnel C (pp)", 100, 1), ("sh_ratio_act", "shadow ratio (act)", 1, 2),
]
TERCILE_ROWS = ["p_chain_nogap", "chains_ps_nogap", "scan_nogap", "scan_gap", "chain_precision", "conf_gap", "ds_items_nogap", "topics_measured"]
CLASS_ROWS = ["scan_gap", "chain_precision", "conf_gap", "detect_cause", "f_S", "f_R", "f_C", "ds_items_gap"]


def load_common(tags, results):
    loaded = {t: load_tag(t, results) for t in tags}
    missing = [t for t, d in loaded.items() if not d]
    if missing:
        raise SystemExit(f"no result files for tags {missing}")
    grades = sorted(set.intersection(*(set(d) for d in loaded.values())))
    return grades, {t: {g: d[g] for g in grades} for t, d in loaded.items()}


def same_students(a, b):
    return all(np.array_equal(a[k], b[k]) for k in ("grade", "gap", "theta", "cluster"))


def delta(m_var, m_base, key):
    return m_var[key] - m_base[key]


def _one(c, x):
    """Result of one criterion on one scope entry x = {'base','var','diff','ci95'}."""
    if x is None or x["diff"] is None or x["ci95"][0] is None:
        return {"value": None, "ci": [None, None], "pass": False, "note": "metric not available"}
    k = c.get("scale", 1)
    v, lo, hi = x["diff"] * k, x["ci95"][0] * k, x["ci95"][1] * k
    test = c.get("test", "effect")
    base, var = (None if x["base"] is None else x["base"] * k), (None if x["var"] is None else x["var"] * k)
    if test == "noninferior":                        # the CI bound on the bad side stays inside the margin
        ok = lo >= c["margin"] if c["direction"] == "ge" else hi <= c["margin"]
    elif test == "point_equal":                      # the point difference is (within tol of) zero
        ok = abs(v) <= c.get("tol", 0.0)
    elif test == "level":                            # the variant's own level (point estimate)
        ok = var is not None and (var >= c["threshold"] if c["direction"] == "ge" else var <= c["threshold"])
    elif test == "effect_positive":                  # direction of the point difference only
        ok = v > 0 if c["direction"] == "ge" else v < 0
    else:                                            # effect: large enough AND the CI beyond 0 in the right direction
        if c["direction"] == "ge":
            ok = v >= c["min_effect"] and lo > 0
        else:
            ok = v <= c["min_effect"] and hi < 0
        if ok and c.get("min_ratio") is not None:
            ok = base is not None and var is not None and var >= c["min_ratio"] * base
        if ok and c.get("min_value") is not None:
            ok = var is not None and var >= c["min_value"]
    return {"value": v, "ci": [lo, hi], "base": base, "var": var, "pass": bool(ok)}


def evaluate_criteria(crit, diffs, grades=()):
    """diffs[scope][metric] = {'base','var','diff','ci95'}; returns one result per criterion.  scope EACH_GRADE: the criterion
    must hold in every grade (student-bootstrap CI), the reported value is the worst grade."""
    out = []
    for c in crit["criteria"]:
        if c["scope"] == "EACH_GRADE":
            rows = [(g, _one(c, diffs.get(f"G{g}", {}).get(c["metric"]))) for g in grades]
            ok = bool(rows) and all(r["pass"] for _, r in rows)
            worst = min((r for _, r in rows if r["value"] is not None), key=lambda r: r["ci"][0] if c["direction"] == "ge" else -r["ci"][1],
                        default={"value": None, "ci": [None, None]})
            bad = [f"G{g}" for g, r in rows if not r["pass"]]
            out.append({**c, "value": worst["value"], "ci": worst["ci"], "pass": ok, "per_grade": {f"G{g}": r for g, r in rows},
                        "note": ("fails in " + ", ".join(bad)) if bad else ""})
        else:
            out.append({**c, **_one(c, diffs.get(c["scope"], {}).get(c["metric"]))})
    return out


def compare_main(a):
    crit = json.loads(Path(a.accept).read_text())
    tags = [a.base] + list(a.variants)
    grades, data = load_common(tags, a.results)
    hier, arrays = hierarchy(), {}
    for t in tags:
        arrays[t], cols, aux = build_arrays(data[t], None, hier)
    base = arrays[a.base]
    for t in a.variants:
        if not same_students(base, arrays[t]):
            raise SystemExit(f"{t}: students/gap assignment differ from {a.base} (different seed, n or stand?)")
    N = len(base["grade"])
    rng = np.random.default_rng(a.seed)
    w1 = np.ones((1, N), np.float32)
    w_stu = student_weights(base, a.n_boot, rng)
    w_clu = cluster_weights(base, cols, a.n_boot, rng)
    scopes = {"ALL": (np.ones(N, bool), w_clu)}
    for t_, name in enumerate(("T1", "T2", "T3")):
        scopes[f"ALL_{name}"] = (base["terc"] == t_, w_clu)
    for g in grades:
        scopes[f"G{g}"] = (base["grade"] == g, w_stu)
    for k, c in enumerate(CLASSES):                       # gap students of one class only (no gap-free students in the scope)
        if ((base["cls"] == k) & base["gapb"]).any():
            scopes[f"CLS_{c}"] = (((base["cls"] == k) & base["gapb"]), w_clu)
    nog = ~base["gapb"]
    dep = nog | (base["gapb"] & np.isin(base["cls"], [CLASSES.index("eligible"), CLASSES.index("non_eligible")]))
    if (dep & base["gapb"]).any():
        scopes["DEP"] = (dep, w_clu)                      # gaps WITH dependants (+ all gap-free students for fp)
        if 9 in grades:
            scopes["DEP_G9"] = (dep & (base["grade"] == 9), w_stu)
    elig = nog | (base["gapb"] & (base["cls"] == CLASSES.index("eligible")))
    if (elig & base["gapb"]).any():
        scopes["ELIG"] = (elig, w_clu)                    # eligible-dependant gaps (+ gap-free students)

    def metr(A, scope):
        m, w = scopes[scope]
        return metrics(A, cols, w1, m), metrics(A, cols, w, m)

    base_m = {sc: metr(base, sc) for sc in scopes}
    results, verdicts = {}, {}
    for t in a.variants:
        res = {}
        for sc in scopes:
            pt_v, bt_v = metr(arrays[t], sc)
            pt_b, bt_b = base_m[sc]
            res[sc] = {}
            for key in pt_v:
                d_pt, d_bt = pt_v[key] - pt_b[key], bt_v[key] - bt_b[key]
                res[sc][key] = {"base": float(pt_b[key][0]) if np.isfinite(pt_b[key][0]) else None,
                                "var": float(pt_v[key][0]) if np.isfinite(pt_v[key][0]) else None,
                                "diff": float(d_pt[0]) if np.isfinite(d_pt[0]) else None, "ci95": ci(d_bt)}
        results[t] = res
        ev = evaluate_criteria(crit, res, grades)
        prim_ok = all(e["pass"] for e in ev if e["kind"] == "primary")
        guard_ok = all(e["pass"] for e in ev if e["kind"] == "guardrail")
        verdicts[t] = {"criteria": ev, "primary_ok": prim_ok, "guardrails_ok": guard_ok,
                       "secondary_passed": sum(1 for e in ev if e["kind"] == "secondary" and e["pass"]),
                       "advance": bool(prim_ok and guard_ok)}

    heads = ["ALL"] + [f"G{g}" for g in grades]
    cell = lambda x, k, p, ci_on=True: ("n/a" if x is None or x["diff"] is None else
                                        f"{x['diff'] * k:+.{p}f}" + (f"[{x['ci95'][0] * k:+.{p}f},{x['ci95'][1] * k:+.{p}f}]"
                                        + ("*" if x['ci95'][0] > 0 or x['ci95'][1] < 0 else "") if ci_on and x['ci95'][0] is not None else ""))
    L = [f"{a.stage}: variants minus base {a.base}, grades {grades}, N={N} students ({int(base['gap'].sum())} with gap), n_boot={a.n_boot}",
         "paired (same students, same replicate); ALL / terciles / classes = cluster bootstrap by gap L3, G<n> = student bootstrap; "
         "diff[95% CI], * = CI excludes 0",
         f"acceptance criteria: {a.accept} (ADVANCE only if every PRIMARY and every GUARDRAIL passes; SECONDARY is reported)"]
    L += ["NOTE " + n for n in crit.get("notes", [])]
    for t in a.variants:
        res = results[t]
        L += ["", f"=== {t} vs {a.base}"]
        L += [f"{'metric':26s}" + "".join(f"{h:>26s}" for h in heads)]
        for key, label, k, p in COMPARE_ROWS:
            L.append(f"{label:26s}" + "".join(f"{cell(res[h].get(key), k, p, ci_on=True):>26s}" for h in heads))
        L += ["", "  by theta tercile (ALL, cluster bootstrap; pp for rates)", f"{'metric':26s}" + "".join(f"{h:>26s}" for h in ("T1 weak", "T2", "T3 strong"))]
        for key in TERCILE_ROWS:
            k = 1 if key.startswith(("chains_ps", "ds_items", "topics")) else 100
            L.append(f"{key:26s}" + "".join(f"{cell(res[f'ALL_{n}'].get(key), k, 2 if k == 1 else 1):>26s}" for n in ("T1", "T2", "T3")))
        cls_present = [c for c in CLASSES if f"CLS_{c}" in res]
        if cls_present:
            L += ["", "  by gap-L3 class (gap students only)", f"{'metric':26s}" + "".join(f"{c:>26s}" for c in cls_present)]
            for key in CLASS_ROWS:
                k = 1 if key.startswith("ds_items") else 100
                L.append(f"{key:26s}" + "".join(f"{cell(res[f'CLS_{c}'].get(key), k, 2 if k == 1 else 1):>26s}" for c in cls_present))
        v = verdicts[t]
        L += ["", f"  acceptance: PRIMARY {'OK' if v['primary_ok'] else 'FAIL'}, GUARDRAILS {'OK' if v['guardrails_ok'] else 'FAIL'}, "
                  f"secondary {v['secondary_passed']}/{sum(1 for e in v['criteria'] if e['kind'] == 'secondary')} -> "
                  f"{'ADVANCE' if v['advance'] else 'DROP'}"]
        for e in v["criteria"]:
            if e["value"] is None:
                val = "n/a"
            elif e.get("test") == "level":
                val = f"level {e['var']:.2f}"
            else:
                val = f"{e['value']:+.2f}[{e['ci'][0]:+.2f},{e['ci'][1]:+.2f}]"
            thr = e.get("margin", e.get("min_effect", e.get("threshold", e.get("tol", ""))))
            extra = f" ratio>={e['min_ratio']} value>={e['min_value']} (var {e['var']:.2f}, base {e['base']:.2f})" if e.get("min_ratio") and e.get("var") is not None else ""
            L.append(f"   {'PASS' if e['pass'] else 'FAIL'} {e['id']:3s} {e['kind']:9s} {e['label'][:70]:70s} {val:>28s}  ({e.get('direction', e.get('test'))} {thr}){extra} {e.get('note', '')}")
    text = "\n".join(L) + "\n"
    out = a.results / f"rootcause_{a.stage}_compare"
    json.dump({"base": a.base, "variants": a.variants, "grades": grades, "n_students": N, "n_boot": a.n_boot, "criteria_file": str(a.accept),
               "criteria": crit, "verdicts": verdicts, "results": results}, open(str(out) + ".json", "w"), ensure_ascii=False, indent=1)
    Path(str(out) + ".txt").write_text(text)
    print(text)


def consistency_main(a):
    """Finalists: stand A, stand B seed 1 and stand B seed 2 must agree - every PRIMARY criterion has the right sign
    in each comparison and no GUARDRAIL is breached in any of them."""
    import re
    crit = json.loads(Path(a.accept).read_text())
    prim = [c for c in crit["criteria"] if c["kind"] == "primary"]
    L, report = [f"consistency of finalists {a.consistency} over {a.stages} (primary: same sign as required; guardrails: no breach)"], {}
    for arm in a.consistency:
        pat = re.compile(rf"^(B_)?{re.escape(arm)}(_?s\d+)?$")
        sources, missing = [], []
        for stage in a.stages:
            f = Path(a.results) / f"rootcause_{stage}_compare.json"
            d = json.loads(f.read_text()) if f.exists() else {"verdicts": {}}
            hit = [(k, v) for k, v in d["verdicts"].items() if pat.match(k)]
            (sources.append((stage,) + hit[0]) if hit else missing.append(stage))
        L += ["", f"=== {arm}" + (f"  MISSING comparisons: {missing}" if missing else "")]
        ok = not missing and bool(sources)
        for stage, var, v in sources:
            cells, right = [], True
            for c in prim:
                e = next(x for x in v["criteria"] if x["id"] == c["id"])
                good = e["value"] is not None and (e["value"] <= 0 if c["direction"] == "le" else e["value"] >= 0)
                right &= good
                cells.append(f"{c['id']} {'-' if e['value'] is None else format(e['value'], '+.2f')}{'' if good else ' WRONG SIGN'}")
            L.append(f"  {stage:12s} {var:10s} " + " | ".join(cells) + f" | primary pass {v['primary_ok']} | guardrails {'OK' if v['guardrails_ok'] else 'BREACH'}")
            ok &= right and v["guardrails_ok"]
        report[arm] = {"consistent": bool(ok), "sources": [s_[:2] for s_ in sources], "missing": missing}
        L.append(f"  -> {'CONSISTENT' if ok else 'NOT CONSISTENT'}")
    text = "\n".join(L) + "\n"
    out = Path(a.results) / "rootcause_stage3c_consistency"
    Path(str(out) + ".txt").write_text(text)
    json.dump({"stages": a.stages, "result": report}, open(str(out) + ".json", "w"), indent=1)
    print(text)


def _r(r, num, den):
    a, b = r[num]["v"], r[den]["v"]
    return 100 * a / b if (a is not None and b) else float("nan")


if __name__ == "__main__":
    main()
