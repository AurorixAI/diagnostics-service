#!/usr/bin/env python
"""Honesty <-> completeness table of Deep Scan arms from rootcause_diag compare files.

  python tools/rootcause_curve.py A0=stage3b_ext:A3 A6=stage3b_ext:A6 ... [--out tools/sim_results/rootcause_curve.txt]

Each item LABEL=STAGE:VARIANT reads tools/sim_results/rootcause_<STAGE>_compare.json and prints the VARIANT's own level and its
difference to that file's base for P1 (T1 P(any chain | no gap)), P2 (chains per gap-free student), P3 (chain_precision), scan rate gap /
no gap, confirmed_gap_is_G among gap students, fp_nogap, cause - fp, acc3 (ALL and worst grade), test length, topics measured, sig_r on
dependent gaps and the acceptance verdict.  `BASE=STAGE` (no colon) prints the base arm of that file.
"""
import argparse
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "sim_results"
COLS = [("P1 T1 chain|nogap %", "ALL_T1", "p_chain_nogap", 100, 1), ("P2 chains/st nogap", "ALL", "chains_ps_nogap", 1, 2),
        ("P3 chain_prec %", "ALL", "chain_precision", 100, 1), ("scan gap %", "ALL", "scan_gap", 100, 1), ("scan nogap %", "ALL", "scan_nogap", 100, 1),
        ("conf_is_G|gap %", "ALL", "conf_gap", 100, 1), ("fp_nogap %", "ALL", "fp_nogap", 100, 2), ("cause-fp pp", "ALL", "signal_cause", 100, 2),
        ("acc3 %", "ALL", "acc_category", 100, 1), ("len", "ALL", "len_mean", 1, 2), ("topics", "ALL", "topics_measured", 1, 2),
        ("sig_r dep pp", "DEP", "signal_root", 100, 1)]


def load(stage):
    return json.loads((RESULTS / f"rootcause_{stage}_compare.json").read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("items", nargs="+")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    head = f"{'arm':6s}" + "".join(f"{c[0]:>20s}" for c in COLS) + f"{'acc3 worst grade d[lo]':>26s}  verdict"
    lines = [head]
    for it in a.items:
        label, spec = it.split("=", 1)
        stage, _, var = spec.partition(":")
        d = load(stage)
        sample = next(iter(d["results"].values()))
        cells, worst = [], None
        for _, scope, m, k, p in COLS:
            if not var:                                   # the base arm of the file
                x = next(iter(d["results"].values()))[scope][m]
                cells.append(f"{x['base'] * k:.{p}f}" if x["base"] is not None else "n/a")
            else:
                x = d["results"][var][scope][m]
                cells.append("n/a" if x["var"] is None else f"{x['var'] * k:.{p}f} ({x['diff'] * k:+.{p}f})")
        if var:
            r = d["results"][var]
            g = {s: r[s]["acc_category"] for s in r if s.startswith("G") and s[1:].isdigit()}
            w = min(g, key=lambda s: g[s]["diff"])
            worst = f"{g[w]['diff'] * 100:+.1f}[{g[w]['ci95'][0] * 100:+.1f}] {w}"
            v = d["verdicts"][var]
            fails = [e["id"] for e in v["criteria"] if e["kind"] in ("primary", "guardrail") and not e["pass"]]
            verdict = ("ADVANCE" if v["advance"] else "DROP") + (f" (fail {','.join(fails)})" if fails else "")
        else:
            worst, verdict = "-", "base"
        lines.append(f"{label:6s}" + "".join(f"{c:>20s}" for c in cells) + f"{worst:>26s}  {verdict}")
    text = "\n".join(lines) + "\n"
    print(text)
    if a.out:
        a.out.write_text(text)


if __name__ == "__main__":
    main()
