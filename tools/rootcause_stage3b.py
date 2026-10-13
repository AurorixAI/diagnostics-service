#!/usr/bin/env python
"""DIAG-1 stage 3b/3c run driver: prints the plan, or runs the arms one after another with a content-bank fingerprint
before and after every run (a run whose bank changed underneath it is flagged INVALID and the driver stops).

  # plan only (nothing is started): commands + expected durations
  python tools/rootcause_stage3b.py plan --stand A
  python tools/rootcause_stage3b.py plan --stand B --seeds 1 2 --arms A0 A3 A5

  # run (sequential, 8 workers each; ~23 min per arm for 7 grades x n=1500; run in the background)
  python tools/rootcause_stage3b.py run --stand A --log tools/sim_results/stage3b_progress.log
  python tools/rootcause_stage3b.py run --stand B --seeds 1 2 --arms A0 A3 A5 --log ...
  python tools/rootcause_stage3b.py run --stand A --arms A0 A6 A7 A8 --reuse-base --log ...   # extra arms vs an existing A0

  # the comparison table with the acceptance verdicts (also printed by `plan`)
  python tools/rootcause_diag.py --base A0 --variants A1 A2 A3 A4 A5 --stage stage3b
  python tools/rootcause_diag.py --consistency A3 A5          # finalists: stand A vs stand B seed 1 vs seed 2 (run after stage 3c)

Arms: tools/rootcause_arms.json (cat_sim --setting overrides per arm).  Tags: stand A seed 1 -> <arm>; stand A other seed ->
<arm>s<seed>; stand B -> B_<arm>_s<seed>.  Result files: tools/sim_results/rootcause_<tag>_G<n>.json (gitignored).
The log lines "=== <tag> ... fp_before: / fp_after:" are read by tools/rootcause_summary.py (fingerprint check).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DIAG = TOOLS.parent
sys.path.insert(0, str(TOOLS))
from rootcause_run import GRADES, RESULTS, content_db_url  # noqa: E402

ARMS = TOOLS / "rootcause_arms.json"
MIN_PER_RUN = 23            # measured: A0 stage-3a, 7 grades x n=1500, 8 workers, idle machine = 1350 s (22.5 min)
COMPARE_MIN = 2             # paired bootstrap (n_boot=2000) per compare call
FP_SQL = {
    "tasks": "select md5(coalesce(string_agg(id||':'||is_active::text||':'||coalesce(updated_at::text,''), ',' order by id),'')) from tasks_master",
    "kh": "select md5(coalesce(string_agg(id||':'||is_active::text||':'||coalesce(importance::text,''), ',' order by id),'')) from knowledge_hierarchy",
    "prereq": "select md5(coalesce(string_agg(skill_id||'>'||prerequisite_id||':'||dependency_type, ',' order by skill_id, prerequisite_id),'')) from skill_prerequisites",
}


def tag_for(stand, arm, seed):
    if stand == "B":
        return f"B_{arm}_s{seed}"
    return arm if seed == 1 else f"{arm}s{seed}"


def run_cmd(stand, arm, seed, overrides, workers):
    tag = tag_for(stand, arm, seed)
    cmd = [sys.executable, "tools/rootcause_run.py", "run", "--tag", tag, "--workers", str(workers)]
    if stand == "B":
        cmd += ["--stand-set", "B"]
    if seed != 1:
        cmd += ["--seed", str(seed)]
    for kv in overrides:
        cmd += ["--setting", kv]
    return tag, cmd


def fingerprint():
    from sqlalchemy import create_engine, text
    eng = create_engine(content_db_url(None))
    with eng.connect() as c:
        out = {k: c.execute(text(q)).scalar()[:8] for k, q in FP_SQL.items()}
    eng.dispose()
    return " ".join(f"{k}={v}" for k, v in out.items())


def compare_cmd(stand, base, variants, seed, stage):
    t = lambda a: tag_for(stand, a, seed)
    return [sys.executable, "tools/rootcause_diag.py", "--base", t(base), "--variants", *[t(v) for v in variants],
            "--stage", stage]


def build(a):
    arms = json.loads(ARMS.read_text())["arms"]
    names = a.arms or list(arms)
    for n in names:
        if n not in arms:
            raise SystemExit(f"unknown arm {n} (known: {list(arms)})")
    runs = [(seed, n) for seed in a.seeds for n in (names[1:] if getattr(a, "reuse_base", False) else names)]
    return arms, names, runs


def cmd_plan(a):
    arms, names, runs = build(a)
    base = names[0]
    print(f"stand {a.stand}, seeds {a.seeds}, arms {names}; {len(runs)} runs x ~{MIN_PER_RUN} min (7 grades, n=1500, {a.workers} workers) "
          f"= ~{len(runs) * MIN_PER_RUN / 60:.1f} h sequential (arms must not run in parallel: they share the 10 cores)")
    for seed, n in runs:
        tag, cmd = run_cmd(a.stand, n, seed, arms[n], a.workers)
        print(f"[{tag}] " + " ".join(cmd[1:]))
    for seed in a.seeds:
        stage = f"stage3{'c' if a.stand == 'B' else 'b'}" + (f"_s{seed}" if a.stand == "B" or seed != 1 else "")
        print(f"[compare seed {seed}] " + " ".join(compare_cmd(a.stand, base, names[1:], seed, stage)[1:])
              + f"   (~{COMPARE_MIN} min per variant; writes tools/sim_results/rootcause_{stage}_compare.txt/.json)")


def cmd_run(a):
    arms, names, runs = build(a)
    log = Path(a.log)
    log.parent.mkdir(parents=True, exist_ok=True)

    def say(msg):
        print(msg, flush=True)
        with open(log, "a") as fh:
            fh.write(msg + "\n")

    for seed, n in runs:
        tag, cmd = run_cmd(a.stand, n, seed, arms[n], a.workers)
        before = fingerprint()
        say(f"=== {tag} start {time.strftime('%F %T')} fp_before: {before}")
        t0 = time.time()
        if shutil.which("caffeinate"):                    # macOS: a sleeping machine expires the fake-redis sessions (seen in 3c)
            cmd = ["caffeinate", "-i", *cmd]
        r = subprocess.run(cmd, cwd=str(DIAG), capture_output=True, text=True)
        after = fingerprint()
        say(f"=== {tag} end {time.strftime('%F %T')} {time.time() - t0:.0f}s rc={r.returncode} fp_after: {after}")
        if r.returncode != 0:
            say((r.stderr or r.stdout)[-1500:])
            sys.exit(1)
        if before != after:
            say(f"INVALID: the content bank changed while {tag} was running; stop, re-run it on a stable bank")
            sys.exit(2)
    base = names[0]
    for seed in a.seeds:
        stage = a.stage or (f"stage3{'c' if a.stand == 'B' else 'b'}" + (f"_s{seed}" if a.stand == "B" or seed != 1 else ""))
        subprocess.run(compare_cmd(a.stand, base, list(a.also or []) + names[1:], seed, stage), cwd=str(DIAG))
    if a.stand == "B" and len(names) > 1:           # finalists: stand A vs stand B seed 1 vs seed 2 (needs the stage3b stand-A comparison)
        subprocess.run([sys.executable, "tools/rootcause_diag.py", "--consistency", *names[1:]], cwd=str(DIAG))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        p = sp.add_parser(name)
        p.add_argument("--stand", choices=["A", "B"], default="A")
        p.add_argument("--seeds", type=int, nargs="+", default=[1])
        p.add_argument("--arms", nargs="*", help="first = base; default: all arms of rootcause_arms.json")
        p.add_argument("--workers", type=int, default=8)
        p.add_argument("--reuse-base", action="store_true", help="the first arm is only the comparison base: its result files already exist, do not re-run it")
        if name == "run":
            p.add_argument("--stage", help="name of the comparison output (default stage3b / stage3c_s<seed>)")
            p.add_argument("--also", nargs="*", help="already-run arms added to the comparison (e.g. A3)")
            p.add_argument("--log", default=str(RESULTS / "stage3b_progress.log"))
    a = ap.parse_args()
    {"plan": cmd_plan, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
