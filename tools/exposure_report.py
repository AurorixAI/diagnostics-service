#!/usr/bin/env python
"""Task exposure of simulated diagnostics: how often each item is served, and how concentrated the served items are.

  python tools/exposure_report.py --tag A0 [--grades 5 6 7 8 9 10 11] [--results tools/sim_results]

Reads the per-student ``served`` lists of tools/sim_results/rootcause_<tag>_G<n>.json (written by cat_sim / rootcause_run) and writes

  tools/sim_results/exposure_<tag>.tsv           one row per task, sorted by exposure (descending):
        task_id, skill_id, exposure (times served = sessions it appeared in: an item is never repeated inside a session),
        share_of_sessions (exposure / all simulated sessions of the selected grades), by_grade (grade:count), phases
        (phase:count), deep_scan_share, correct_rate
  tools/sim_results/exposure_<tag>_coverage.tsv  one row per grade: sessions, served items, distinct tasks served, tasks in
        the bank for the grade (active tasks of G<n>_ skills; blank when the DB is unreachable), and how many distinct tasks
        cover 50 / 80 / 95 % of all items served in that grade's sessions (most exposed tasks first), top-1 / top-10 share.

Exposure is a property of the simulated population (theta ~ N(0,1), one gap L3 for half of the students) and of the bank state at
run time; it is not the exposure of real students.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from rootcause_run import GRADES, RESULTS, content_db_url  # noqa: E402

LEVELS = (0.50, 0.80, 0.95)


def load_students(tag, grades, results):
    out = {}
    for g in grades:
        p = Path(results) / f"rootcause_{tag}_G{g}.json"
        if p.exists():
            out[g] = json.load(open(p))["arms"]["A"]["students"]
    return out


def n_to_cover(counts, share):
    """Smallest number of tasks (most exposed first) whose served items reach ``share`` of all served items."""
    total, acc = sum(counts), 0
    for i, c in enumerate(sorted(counts, reverse=True), 1):
        acc += c
        if acc >= share * total:
            return i
    return len(counts)


def bank_sizes(grades):
    try:
        from sqlalchemy import create_engine, text
        eng = create_engine(content_db_url(None))
        with eng.connect() as c:
            rows = c.execute(text("select substring(skill_id from '^G[0-9]+') g, count(*) from tasks_master "
                                  "where is_active and skill_id ~ '^G[0-9]+_' group by 1")).all()
        eng.dispose()
        return {int(r[0][1:]): int(r[1]) for r in rows}
    except Exception as e:                       # the report must not depend on the DB
        print(f"bank sizes unavailable: {e!r}", file=sys.stderr)
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--grades", type=int, nargs="*", default=GRADES)
    ap.add_argument("--results", type=Path, default=RESULTS)
    a = ap.parse_args()
    data = load_students(a.tag, a.grades, a.results)
    if not data:
        raise SystemExit(f"no result files for tag {a.tag}")
    if not all("served" in r for st in data.values() for r in st[:1]):
        raise SystemExit("the result files carry no `served` lists: re-run the arm with the current tools/cat_sim.py")

    n_sessions = sum(len(st) for st in data.values())
    expo = Counter()
    skill, by_grade, phases = {}, defaultdict(Counter), defaultdict(Counter)
    correct, deep = Counter(), Counter()
    per_grade_counts = {}
    for g, students in data.items():
        gc = Counter()
        for r in students:
            for it in r["served"]:
                t = it["task_id"]
                expo[t] += 1
                gc[t] += 1
                skill.setdefault(t, it["skill_id"])
                by_grade[t][g] += 1
                phases[t][it["phase"]] += 1
                correct[t] += int(it["correct"])
                deep[t] += int(it["is_deep_scan"])
        per_grade_counts[g] = gc

    out = a.results / f"exposure_{a.tag}.tsv"
    with open(out, "w") as fh:
        fh.write("task_id\tskill_id\texposure\tshare_of_sessions\tby_grade\tphases\tdeep_scan_share\tcorrect_rate\n")
        for t, n in sorted(expo.items(), key=lambda kv: (-kv[1], kv[0])):
            fh.write("\t".join([
                t, skill[t], str(n), f"{n / n_sessions:.4f}",
                ",".join(f"G{g}:{c}" for g, c in sorted(by_grade[t].items())),
                ",".join(f"{p}:{c}" for p, c in phases[t].most_common()),
                f"{deep[t] / n:.3f}", f"{correct[t] / n:.3f}"]) + "\n")

    bank = bank_sizes(data)
    cov = a.results / f"exposure_{a.tag}_coverage.tsv"
    lines = ["grade\tsessions\tserved_items\tdistinct_tasks\ttasks_in_bank\tn50\tn80\tn95\ttop1_share\ttop10_share"]
    for g, gc in sorted(per_grade_counts.items()):
        counts = list(gc.values())
        total = sum(counts)
        top = sorted(counts, reverse=True)
        lines.append("\t".join([f"G{g}", str(len(data[g])), str(total), str(len(gc)), str(bank.get(g, "")),
                                *(str(n_to_cover(counts, s)) for s in LEVELS),
                                f"{top[0] / total:.4f}", f"{sum(top[:10]) / total:.4f}"]))
    cov.write_text("\n".join(lines) + "\n")
    print(f"{n_sessions} sessions, {len(expo)} distinct tasks served -> {out}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
