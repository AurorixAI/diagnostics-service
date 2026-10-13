# cat_sim — CAT diagnostic simulation harness

`tools/cat_sim.py` runs the real `SessionService` (warm-up, navigation, stop rules,
Deep Scan), `AnswerEvaluator`, `alpha_engine`, `level_policy` and
`report_generator._reconstruct_root_cause_chains` against the real content-service
read API (`content_router` mounted in-process behind a starlette `TestClient`) on a
content Postgres DB, with simulated students. Prod-equivalent settings are forced
(MAX_ITEMS=42, WARMUP=5, MIN_ITEMS=12, MIN_SECTION_COVERAGE=5, CLASSIFICATION 20/0.40/0.90,
DEEP_SCAN_SESSION_BUDGET=6); override with `--setting KEY=VAL`.

## Setup

```
uv venv --python 3.11 V
uv pip install --python V/bin/python -r diagnostic-service/requirements.txt fakeredis
```

## CLI

```
# one arm (e.g. G10 sanity)
V/bin/python tools/cat_sim.py --grade 10 --n-students 2000 --seed 1 \
    --content-db-url postgresql://USER:PW@localhost:5434/algo_content --out /tmp/g10.json

# A/B: scratch copy of the DB (CREATE DATABASE ... TEMPLATE, dropped at the end) + edges
# from a JSON {"prerequisites": [{skill_id, prerequisite_id, weight, criticality, ...}]};
# arm A = original DB, arm B = copy + edges; paired bootstrap of B - A
V/bin/python tools/cat_sim.py --grade 11 --n-students 3000 --seed 1 \
    --content-db-url postgresql://USER:PW@localhost:5434/algo_content \
    --add-edges path/to/edges.json --out /tmp/ab.json

# same, but apply a content_repairs manifest on the scratch copy with the real
# tools.content_review.guarded_repair --execute (combinable with --add-edges); gap L3 "auto" =
# active G<grade> L3s that have active tasks in every arm; --deactivate-empty-l4 = counterfactual
V/bin/python tools/cat_sim.py --grade 9 --n-students 3000 --seed 1 --gap-l3 auto \
    --content-db-url postgresql://USER:PW@localhost:5434/algo_content \
    --apply-manifest ../content-service/data/content_repairs/MANIFEST.json --backup-path /tmp/bk.json

# compare two saved single-arm runs
V/bin/python tools/cat_sim.py --compare a.json b.json
```

Other flags: `--workers` (processes, default 8), `--gap-l3 ID...`, `--gap-fraction` (0.5),
`--gap-fail-p` (0.85), `--dependant-depth` (1 = direct dependants, 0 = transitive),
`--truth-db-url`, `--scratch-db`, `--n-boot`.
Never point `--content-db-url` at a DB you cannot afford to read; the harness only
reads it (the A/B mode writes only to the scratch copy).

## Stubbed

Per-session Redis answer lock (single-threaded; fakeredis has no Lua), diagnostic
Postgres persistence (in-memory repos holding the real ORM objects), report/auth-sync
job queues and threads, `auth_client`, LLM narrative, and the report's
`_load_task_context`. Redis state itself is real JSON round-trip on fakeredis.

## Student and gap model

True theta ~ N(0,1); P(correct) = `alpha_engine._p3pl` with the served task's IRT
parameters. With probability `--gap-fraction` one L3 from `--gap-l3` (default for
G11: P16, P17, P20, P01, P09, P11, P12, P35) is injected: tasks under that L3 and
under its dependants in the ground-truth prerequisite graph (the arm-B DB; direct
dependants by default) are answered wrongly with p = 0.85 regardless of theta.
Responses are a hash of (seed, student, task), the content-DB RANDOM() is seeded per
student, so the same student behaves identically in every arm and reruns are
bit-identical.

## Metrics

3-band and 5-band level accuracy (`level_policy.classify(true theta)` vs final),
RMSE/bias of theta, mean/p90 length, all-sections coverage, deep-scan items,
root-cause detection among gap students: `detect_cause` (a Deep-Scan step under the
injected L3 failed inside a chain; headline), `detect_root` (strict: it is the
chain's `root_gap_skill_id`), `detect_named` (any failed step incl. the scan origin),
`coherent_session_share` / `coherent_entry_share` (report weak topics, and their Deep-Scan detail skills, backed
by a failed answer whose task sits there in the truth tree = arm-B DB), `bg_chain_nogap` (gap-free students whose chain root lies in the candidate set; not a
pure false-positive rate). Differences use a paired bootstrap (resampling students).

## Stage-3a instrumentation (DIAG-1)

Every student record also carries read-only trace fields; none of the core fields depends on them (checked: OC15 grade 10,
1500 students, all 32 core fields identical with and without the trace). The session state is only read from the fake redis
after each answer.

* `l3_visits` - one entry per L3 visit of the navigation phase: `l3, importance, n_items, n_wrong, mean_p_hat` (+ `n_l4, score,
  resid = sum(p_hat - x), failed, complete, terminal, sig`). `p_hat = _p3pl(theta_before, a, b, c)` with the session's theta
  before the answer. `sig` = the L3 is the injected gap G or one of its direct dependants (gap students fail those).
  `complete = False`: the session ended inside the visit; `terminal = True`: it ended with the visit's last answer (the
  service may not have decided it; excluded from the shadow statistics).
* `shadow_triggers` - for every failed decided L3: `cur` (importance >= threshold and a failing skill; budget ignored),
  `d1` (>= 2 wrong in the L3, or 1 wrong when it has a single L4), `d2` (`resid >= 1.0`), `imp_ok`, `budget_spent`,
  `actual` (a scan really started), `sig`.
* `scan_log` - each scan: `budget_used` at its start, `origin_l3`, initial prerequisite queue (`queue`, `queue_l3`),
  `G_in_queue` / `G_pos`, `steps` (probed skill, L3, outcome, `gap_confirmed`, attempts), `G_origin` / `G_probed` / `G_confirmed`.
* `chain_roots`, `chain_sources`, `confirmed_l3s`, `named_l2s`, `n_weak_topics`, `n_crit_topics`, `n_detail_skills`, `trace_aux`
  (self-checks: replayed navigator vs item count, predicted vs observed trigger; both 0).

`tools/rootcause_diag.py --tag A0 --stage stage3a` turns them into the metric tables (cluster bootstrap by gap L3 for ALL
grades, student bootstrap per grade); `tools/rootcause_stand_b.py` generates stand B (8 seeded gap L3 per grade).

`served` (per student): every item served, in order - `{task_id, skill_id, phase, is_deep_scan, correct}`. `tools/exposure_report.py --tag A0`
aggregates it into `tools/sim_results/exposure_<tag>.tsv` (per task: exposure, share of sessions, phases) and `exposure_<tag>_coverage.tsv`
(per grade: distinct tasks, and how many cover 50/80/95% of the served items).
