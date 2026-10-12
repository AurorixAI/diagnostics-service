#!/usr/bin/env python
"""Root-cause study: generate STAND B (tools/rootcause_stand.json -> "stand_b") from the content graph.

Stand A (the hand-picked "grades" section) stays untouched.  Stand B is a deterministic, seeded draw of 8 gap L3 per grade
that separates the three situations the Deep Scan trigger meets (rule, applied per grade 5..11, read-only on the content DB):

  visitable L3  = active L3 with >=1 active L4 that has an active task.
  dependant     = visitable L3 of the SAME grade with a HARD prerequisite edge to the gap L3 (in-grade, direct): the L3s
                  that gap students fail together with the gap in the simulation (cat_sim --dependant-depth 1) and
                  the only ones a grade-g session can visit.
  class (of a candidate gap L3 G):
     eligible      : G has a dependant with importance >= IMPORTANCE_THRESHOLD (8)  -> a failed dependant can start a scan
                     that reaches G through its prerequisite queue          (3 per grade)
     non_eligible  : G has dependants, all with importance < 8: a failed dependant never starts a scan   (3 per grade)
     typical       : G has no dependant at all                                                       (2 per grade)
  candidate quality tiers (stand-A rule first, relaxed only when a class cannot be filled):
     T1 >=3 active L4 with tasks and >=80 active tasks; T2 >=2 L4 and >=40 tasks; T3 >=1 L4 and >=20 tasks.
  draw: for each class in the order eligible, non_eligible, typical and each tier T1..T3, the candidates (sorted by id) are
     shuffled with random.Random(f"{SEED}:{grade}:{class}:{tier}") and taken in that order while the class has free slots and
     the candidate is neither a dependant nor a prerequisite (hard, in-grade) of an already chosen L3.
  shortfall: a class that no tier can fill (G10 has no non_eligible candidate: every in-grade dependant has importance >= 8)
     hands its free slots to the eligible class (label "eligible_fill", drawn by the same seeded rule, tier order unchanged).
  gap_l3 order: eligible, eligible_fill, non_eligible, typical (the simulation draws G uniformly from this list).

  python tools/rootcause_stand_b.py            # print the draw
  python tools/rootcause_stand_b.py --write    # (re)write the "stand_b" section of tools/rootcause_stand.json
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text

TOOLS = Path(__file__).resolve().parent
DIAG = TOOLS.parent
STAND = TOOLS / "rootcause_stand.json"
SEED = 20261012
IMPORTANCE_THRESHOLD = 8
GRADES = [5, 6, 7, 8, 9, 10, 11]
QUOTA = {"eligible": 3, "non_eligible": 3, "typical": 2}
TIERS = {"T1": (3, 80), "T2": (2, 40), "T3": (1, 20)}      # (min active L4 with tasks, min active tasks)


def content_db_url():
    for line in (DIAG.parent / "content-service" / ".env").read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DATABASE_URL not found")


def grade_of(i):
    return int(re.match(r"G(\d+)_", i).group(1))


def load(url):
    eng = create_engine(url)
    with eng.connect() as c:
        l3 = c.execute(text(
            "select k.id, k.importance, count(distinct l4.id), count(t.id) from knowledge_hierarchy k "
            "join knowledge_hierarchy l4 on l4.parent_id=k.id and l4.is_active and l4.level='L4' "
            "join tasks_master t on t.skill_id=l4.id and t.is_active "
            "where k.level='L3' and k.is_active group by k.id, k.importance")).all()
        edges = c.execute(text("select skill_id, prerequisite_id from skill_prerequisites "
                               "where dependency_type='hard'")).all()
    eng.dispose()
    info = {r[0]: {"importance": int(r[1] or 5), "n_l4": int(r[2]), "n_tasks": int(r[3])} for r in l3}
    deps, pre = defaultdict(set), defaultdict(set)       # prerequisite -> dependants, dependant -> prerequisites
    for s, p in edges:
        if s in info and p in info and s != p and grade_of(s) == grade_of(p):
            deps[p].add(s); pre[s].add(p)
    return info, deps, pre


def classify(i, info, deps):
    d = deps.get(i, set())
    if not d:
        return "typical"
    return "eligible" if any(info[x]["importance"] >= IMPORTANCE_THRESHOLD for x in d) else "non_eligible"


def draw_grade(g, info, deps, pre, seed=SEED):
    ids = sorted(i for i in info if grade_of(i) == g)
    cls = {i: classify(i, info, deps) for i in ids}
    chosen, labels, tiers_used = [], {}, {}

    def conflicts(i):
        return any(j in deps.get(i, ()) or j in pre.get(i, ()) for j in chosen)

    def fill(label, source_class, n):
        got = 0
        for tier, (min_l4, min_t) in TIERS.items():
            if got >= n:
                break
            cand = [i for i in ids if cls[i] == source_class and i not in chosen
                    and info[i]["n_l4"] >= min_l4 and info[i]["n_tasks"] >= min_t]
            random.Random(f"{seed}:{g}:{source_class}:{tier}").shuffle(cand)
            for i in cand:
                if got >= n:
                    break
                if conflicts(i):
                    continue
                chosen.append(i); labels[i] = label; tiers_used[i] = tier; got += 1
        return got

    short = 0
    for c in ("eligible", "non_eligible", "typical"):
        got = fill(c, c, QUOTA[c])
        if got < QUOTA[c]:
            short += QUOTA[c] - got
    if short:                                       # shortfall slots -> eligible_fill
        got = fill("eligible_fill", "eligible", short)
        assert got == short, f"G{g}: cannot fill the stand ({short - got} slots left)"
    order = {"eligible": 0, "eligible_fill": 1, "non_eligible": 2, "typical": 3}
    drawn = list(chosen)
    chosen.sort(key=lambda i: (order[labels[i]], drawn.index(i)))
    detail = {}
    for i in chosen:
        d = sorted(deps.get(i, ()))
        detail[i] = {"class": labels[i], "tier": tiers_used[i], "n_active_l4_with_tasks": info[i]["n_l4"],
                     "n_active_tasks": info[i]["n_tasks"], "importance": info[i]["importance"],
                     "in_grade_hard_dependants": [{"id": x, "importance": info[x]["importance"]} for x in d],
                     "trigger_eligible": any(info[x]["importance"] >= IMPORTANCE_THRESHOLD for x in d)}
    pool = {c: sum(1 for i in ids if cls[i] == c) for c in QUOTA}
    return {"gap_l3": chosen, "classes": {c: [i for i in chosen if labels[i] == c] for c in order},
            "candidates_per_class": pool, "detail": detail}


def build(url):
    info, deps, pre = load(url)
    return {
        "description": ("Stand B: 8 gap L3 per grade drawn by a deterministic seeded rule from the content graph "
                        "(tools/rootcause_stand_b.py): 3 eligible-dependant (a direct in-grade hard dependant with "
                        "importance >= 8), 3 non-eligible-dependant (dependants exist, all importance < 8), 2 typical "
                        "(no dependant).  Same params as stand A.  G10 has no non-eligible class: its 3 slots are "
                        "'eligible_fill'."),
        "rule": __doc__.split("\n\n", 1)[1].split("\n\n  python")[0].strip(),
        "seed": SEED, "importance_threshold": IMPORTANCE_THRESHOLD, "quota": QUOTA, "tiers": TIERS,
        "grades": {str(g): draw_grade(g, info, deps, pre) for g in GRADES},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--content-db-url")
    a = ap.parse_args()
    b = build(a.content_db_url or content_db_url())
    for g, v in b["grades"].items():
        print(f"G{g}: {v['gap_l3']}  pool={v['candidates_per_class']}  classes={ {c: len(x) for c, x in v['classes'].items()} }")
    if a.write:
        stand = json.loads(STAND.read_text())
        stand["stand_b"] = b
        STAND.write_text(json.dumps(stand, ensure_ascii=False, indent=1))      # same layout as the existing file
        print("written ->", STAND)


if __name__ == "__main__":
    main()
