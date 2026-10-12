#!/usr/bin/env python
"""CAT diagnostic simulation harness (ALGO diagnostic-service).

Runs the REAL ``SessionService`` (warm-up, topic/subtopic/skill navigation,
stopping rules, Deep Scan) and the REAL ``report_generator.
_reconstruct_root_cause_chains`` against the REAL content-service read API
(``content_router``, mounted in-process behind a starlette ``TestClient``) on top
of a content Postgres database, with simulated students.

What is real / what is stubbed
------------------------------
real    : SessionService (item selection, stop rules, deep scan), AnswerEvaluator,
          alpha_engine (3PL/EAP), level_policy, RedisStateManager (JSON round-trip,
          on fakeredis), content_router SQL, ``_reconstruct_root_cause_chains``.
stubbed : per-session answer lock (single-threaded), diag Postgres persistence (in-memory session/answer repos, same ORM
          objects), report/auth-sync job queue + threads, auth_client, the LLM
          narrative and ``_load_task_context`` of the report (not needed for chains).

Simulated student
-----------------
true theta ~ N(0,1); P(correct) = alpha_engine._p3pl with the served task's IRT
parameters.  Optionally (``--gap-fraction``, default 0.5 if ``--gap-l3`` is known
for the grade) one L3 from ``--gap-l3`` is injected as a prerequisite gap: tasks
whose skill lies under that L3 OR under any DEPENDANT (direct, ``--dependant-depth 1``; 0 = transitive) of it in the
ground-truth prerequisite graph (``--truth-db-url``, default = content db) are
failed with probability ``--gap-fail-p`` (0.85) regardless of theta.
Randomness is paired: the (theta, gap) of student i depend only on (seed, i) and
the response to task t is a hash of (seed, i, t), so the same student answers
the same task identically in every arm.  The content-db RANDOM() used for
tie-breaking is seeded per student (setseed), so a rerun is reproducible.

Metrics per arm
---------------
level-band accuracy (level_policy.classify(true theta) vs session's final
category; 5-band ``status`` too), RMSE/bias of theta, mean/p90 test length, share
of students with all L1 sections covered, deep-scan items, root-cause detection
= share of gap-injected students whose report root-cause chains name the injected L3:
``detect_cause`` = a Deep-Scan step under it was failed inside a chain (headline),
``detect_root`` = strict, its ``root_gap_skill_id`` (deepest failed step; a deeper
failed prerequisite takes the root away), ``detect_named`` = any failed step under it
incl. the scan origin; plus background rate = gap-free students whose chain root lies in the candidate L3 set
(weak-theta students really lack those skills, so this is not a pure false-positive rate).

Setup: uv venv --python 3.11 V && uv pip install --python V/bin/python -r requirements.txt fakeredis
Usage
-----------------------------------------------------------------------------
  # one arm
  python tools/cat_sim.py --grade 10 --n-students 2000 --seed 1 \\
      --content-db-url postgresql://USER:PW@localhost:5434/algo_content \\
      --out /tmp/g10.json
  # A/B: copy the content DB to a scratch DB, add prerequisite edges
  # ({"prerequisites":[{skill_id,prerequisite_id,...}]}), run both arms paired,
  # paired-bootstrap the differences, drop the scratch DB
  python tools/cat_sim.py --grade 11 --n-students 2000 --seed 1 \\
      --content-db-url postgresql://USER:PW@localhost:5434/algo_content \\
      --add-edges ../content-service/data/content_repairs/n01-...-g11-prereqs.json \\
      --out tools/cat_sim_results.json
  # compare two saved single-arm runs
  python tools/cat_sim.py --compare a.json b.json

Known limitations: the diag DB, report LLM and queues are not exercised;
students answer instantly (no time_ms); ``--workers`` processes each open their
own content-db pool.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

DIAG_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONTENT_DIR = DIAG_DIR.parent / "content-service"
DEFAULT_GAP_L3 = {
    11: ["G11_P16", "G11_P17", "G11_P20", "G11_P01", "G11_P09", "G11_P11", "G11_P12", "G11_P35"],
}
PROD_SETTINGS = {
    "MAX_ITEMS": "42", "WARMUP_ITEMS": "5", "MIN_ITEMS": "12", "SE_THRESHOLD": "0.30",
    "MIN_SECTION_COVERAGE": "5", "CLASSIFICATION_MIN_ITEMS": "20",
    "CLASSIFICATION_SE_THRESHOLD": "0.40", "CLASSIFICATION_CONFIDENCE_THRESHOLD": "0.90",
    "DEEP_SCAN_SESSION_BUDGET": "6", "DEEP_SCAN_MAX_ITEMS": "6",
    "DEEP_SCAN_IMPORTANCE_THRESHOLD": "8", "MASTERY_THRESHOLD": "0.6",
}
# Deep Scan flags whose defaults live in the diagnostic-service Settings (variant OC15 since 2026-10-12);
# not pinned here, only reported with the effective settings.
VARIANT_FLAGS = ("DEEP_SCAN_PROBE_DIFFICULTY_OFFSET", "DEEP_SCAN_CONFIRM_PROBES", "DEEP_SCAN_TRIGGER_MODE")
TOKEN = "cat-sim-internal-token"
EFFECTIVE_SETTINGS: Dict[str, Dict[str, Any]] = {}     # arm label -> settings reported by the workers

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap: content-service app and diagnostic-service share the package name
# ``src``.  Import the content router first, park its modules, then import ours.
# ─────────────────────────────────────────────────────────────────────────────
_CTX: Dict[str, Any] = {}


def bootstrap(content_db_url: str, truth_db_url: Optional[str], content_dir: Path,
              extra_settings: Dict[str, str]) -> Dict[str, Any]:
    if _CTX:
        return _CTX
    os.environ.update(PROD_SETTINGS)
    os.environ.update({k.upper(): str(v) for k, v in extra_settings.items()})
    os.environ.update({
        "DATABASE_URL": content_db_url, "INTERNAL_SERVICE_TOKEN": TOKEN,
        "APP_ENV": "testing", "REDIS_URL": "redis://localhost:6379",
    })
    # 1) content-service router
    sys.path.insert(0, str(content_dir))
    from fastapi import FastAPI
    from src.api.content_router import router as content_router  # content-service's src
    parked = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "src" or k.startswith("src.")}
    sys.path.remove(str(content_dir))
    app = FastAPI()
    app.include_router(content_router)
    # 2) diagnostic-service
    sys.path.insert(0, str(DIAG_DIR))
    import fakeredis
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from src.clients import content_client
    from src.core import redis_client
    from src.domain import report_generator as rg
    from src.domain import session_service as ss
    from src.domain import alpha_engine as ae
    from src.domain import level_policy as lp
    from src.models.diag_models import DiagAnswer, DiagSession
    from src.repositories.diag_repo import DiagAnswerRepository, DiagSessionRepository
    from src.state.redis_state import RedisStateManager

    client = TestClient(app, base_url="http://testserver", headers={"X-Internal-Service-Token": TOKEN})
    client.__enter__()                       # keep one portal/event loop alive
    content_client._client = client

    # cache deterministic endpoints (tree, prerequisites, single task); never the
    # random task LIST.  Pure speed-up, identical answers.
    _cache: Dict[Any, Any] = {}
    _orig_get = client.get

    def cached_get(path: str, **kwargs):
        if path.endswith("/tasks"):
            return _orig_get(path, **kwargs)
        key = (path, repr(sorted((kwargs.get("params") or {}).items())))
        r = _cache.get(key)
        if r is None:
            r = _cache[key] = _orig_get(path, **kwargs)
        return r

    content_client.get = cached_get

    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    redis_client._client = fake_redis

    # persistence stubs ------------------------------------------------------
    class NullDb:
        def add(self, *a, **k): pass
        def flush(self, *a, **k): pass
        def commit(self, *a, **k): pass
        def rollback(self, *a, **k): pass
        def delete(self, *a, **k): pass

    class MemSessions(DiagSessionRepository):
        def __init__(self): super().__init__(NullDb()); self.rows = {}
        def add(self, obj): self.rows[obj.id] = obj; return obj
        def get_by_id(self, pk): return self.rows.get(pk)
        def get_fresh(self, sid, *, for_update=False): return self.rows.get(sid)
        def get_by_invite_code(self, code, *, unfinished_only=False): return None

    class MemAnswers(DiagAnswerRepository):
        def __init__(self): super().__init__(NullDb()); self.rows = []
        def log_answer(self, **kw):
            a = DiagAnswer(**kw); self.rows.append(a); return a
        def get_last_answer(self, sid): return self.rows[-1] if self.rows else None

    noop = lambda *a, **k: None
    ss.enqueue_report_generation = noop
    ss.enqueue_auth_completion_sync = noop
    ss.process_next_report_job = noop
    ss.process_next_auth_completion_sync = noop
    rg._load_task_context = lambda answer: (None, "unavailable")

    svc = ss.SessionService(NullDb())
    svc.session_repo = MemSessions()
    svc.answer_repo = MemAnswers()
    svc.redis = RedisStateManager(fake_redis)
    svc.redis.answer_lock = lambda session_id: contextlib.nullcontext()   # single-threaded; fakeredis has no Lua

    # knowledge graph (ground truth) ---------------------------------------
    def load_graph(url):
        eng = create_engine(url)
        with eng.connect() as c:
            nodes = {r[0]: (r[1], r[2]) for r in c.execute(text(
                "select id, level, parent_id from knowledge_hierarchy"))}
            edges = [(r[0], r[1]) for r in c.execute(text(
                "select skill_id, prerequisite_id from skill_prerequisites where dependency_type='hard'"))]
        eng.dispose()
        return nodes, edges

    def load_task_skills(url):
        eng = create_engine(url)
        with eng.connect() as c:
            m = {r[0]: r[1] for r in c.execute(text("select id, skill_id from tasks_master"))}
        eng.dispose()
        return m

    nodes, _ = load_graph(content_db_url)
    tnodes, tedges = load_graph(truth_db_url or content_db_url)
    ttask = load_task_skills(truth_db_url or content_db_url)       # task -> skill in the truth tree

    from src.core import config as diag_config
    _CTX.update(dict(
        svc=svc, rg=rg, ss=ss, ae=ae, lp=lp, content_client=content_client,
        sessions=svc.session_repo, answers=svc.answer_repo, fake_redis=fake_redis,
        nodes=nodes, tnodes=tnodes, tedges=tedges, ttask=ttask, parked=parked, DiagSession=DiagSession,
        settings=diag_config.get_settings(), db_url=content_db_url,
    ))
    return _CTX


def l3_of(nodes: Dict[str, Any], sid: str) -> Optional[str]:
    """L3 ancestor (self when already L3)."""
    seen = 0
    while sid in nodes and seen < 6:
        level, parent = nodes[sid]
        if level == "L3":
            return sid
        if level in ("L2", "L1") or not parent:
            return None
        sid, seen = parent, seen + 1
    return None


def dependants_of(tnodes, tedges, gap: str, max_depth: int = 1) -> set:
    """{gap} + L3s that require it in the truth graph (max_depth hops; 0 = unlimited)."""
    rev: Dict[str, set] = {}
    for s, p in tedges:
        ls, lp_ = l3_of(tnodes, s), l3_of(tnodes, p)
        if ls and lp_ and ls != lp_:
            rev.setdefault(lp_, set()).add(ls)
    out, frontier, depth = {gap}, [gap], 0
    while frontier and (max_depth == 0 or depth < max_depth):
        nxt = []
        for x in frontier:
            for d in rev.get(x, ()):
                if d not in out:
                    out.add(d); nxt.append(d)
        frontier, depth = nxt, depth + 1
    return out


def _u(seed: int, i: int, key: str) -> float:
    h = hashlib.blake2b(f"{seed}:{i}:{key}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2 ** 64


# ─────────────────────────────────────────────────────────────────────────────
# One student
# ─────────────────────────────────────────────────────────────────────────────
def simulate_student(ctx, i: int, seed: int, grade: int, gap_list: List[str],
                     gap_fraction: float, gap_fail_p: float, fail_cache: Dict[str, set], depth: int = 1) -> Dict[str, Any]:
    import random
    from sqlalchemy import text  # noqa: F401
    svc, rg, ae, lp = ctx["svc"], ctx["rg"], ctx["ae"], ctx["lp"]
    cc, nodes = ctx["content_client"], ctx["nodes"]
    rng = np.random.default_rng([seed, i])
    theta = float(rng.normal())
    has_gap = bool(gap_list) and rng.random() < gap_fraction
    gap = gap_list[int(rng.integers(len(gap_list)))] if gap_list else None
    gap = gap if has_gap else None
    if gap and gap not in fail_cache:
        fail_cache[gap] = dependants_of(ctx["tnodes"], ctx["tedges"], gap, depth)
    failset = fail_cache[gap] if gap else set()

    random.seed(f"{seed}:{i}")
    _seed_pg(ctx, seed, i)

    sessions, answers = ctx["sessions"], ctx["answers"]
    sessions.rows.clear(); answers.rows.clear()
    sid, task = svc.create_session(uuid.uuid4(), grade, invite_code=None, prior_theta=0.0)
    mismatches = n = 0
    while True:
        row = cc.get_task(task.task_id).json()
        l3 = l3_of(nodes, task.skill_id)
        p = ae._p3pl(theta, float(row["irt_discrimination"] or 1.0),
                     float(row["irt_difficulty"] or 0.0), float(row["irt_guessing"] or 0.0))
        if l3 in failset:
            want = _u(seed, i, task.task_id + ":gap") >= gap_fail_p
        else:
            want = _u(seed, i, task.task_id + ":irt") < p
        ans = row["correct_answer"] if want else "x_wrong_x"
        res = svc.submit_answer(sid, task.task_id, ans)
        n += 1
        if want and not (res.is_correct and res.outcome >= 1.0):
            mismatches += 1       # evaluator rejected the key itself (bank defect)
        if res.session_completed:
            break
        task = res.next_task
        if n > 200:
            raise RuntimeError("runaway session")

    db = sessions.rows[sid]
    snap = db.state_snapshot or {}
    th_hat, se = float(db.theta), float(db.theta_se)
    cls_true, cls_hat = lp.classify(theta, 0.0, grade), lp.classify(th_hat, se, grade)
    rows = list(answers.rows)
    chains = rg._reconstruct_root_cause_chains(
        rows, {}, [], grade, confirm_probes=(snap.get("deep_scan_params") or {}).get("confirm_probes"))
    gap_set = set(gap_list)
    root_l3 = [l3_of(nodes, c.get("root_gap_skill_id") or "") for c in chains]
    detected = cause = named = False
    if gap:
        detected = gap in root_l3                       # strict: injected L3 is the report's root gap
        for c in chains:
            for st in c["steps"]:
                if (l3_of(nodes, st.get("skill_id") or "") != gap or lp.is_correct(st["outcome"])
                        or st.get("gap_confirmed") is False):   # DEEP_SCAN_CONFIRM_PROBES > 1: wrong but not confirmed
                    continue
                named = True                            # failed step under the L3 anywhere (incl. scan origin)
                if st.get("is_deep_scan"):
                    cause = True                        # found by Deep Scan as a failed prerequisite
    fp = (not gap) and any(r in gap_set for r in root_l3)
    sections = set(snap.get("section_ids") or [])
    # Report coherence: every weak/critical topic (and its Deep-Scan detail skills) named by the
    # report must be backed by a failed answer whose task sits there in the TRUTH tree.
    tn, ttask = ctx["tnodes"], ctx["ttask"]

    def anc(sid, level):
        for _ in range(6):
            if sid not in tn:
                return None
            if tn[sid][0] == level:
                return sid
            sid = tn[sid][1]
        return None
    failed = [a_ for a_ in rows if not lp.is_correct(a_.outcome)]
    f_l2 = {anc(ttask.get(a_.task_id), "L2") for a_ in failed}
    f_l3 = {anc(ttask.get(a_.task_id), "L3") for a_ in failed}
    breakdown = db.topic_breakdown or {}
    _, weak_blk, crit_blk = rg._build_skill_blocks(
        breakdown, list(snap.get("confirmed_gaps") or []), {}, rows,
        l2_of=rg._make_l2_resolver(rg.KnowledgeRepository(), breakdown.keys()))
    entries = coh_entries = 0
    for ent in weak_blk + crit_blk:
        entries += 1
        coh_entries += ent["skill_id"] in f_l2
        for dsk in ent.get("detail_skills") or []:
            entries += 1
            coh_entries += l3_of(tn, dsk["skill_id"]) in f_l3
    gap_topic_named = None
    if gap:
        gt = anc(gap, "L2")
        gap_topic_named = any(e["skill_id"] == gt for e in weak_blk + crit_blk)
    confirmed = list(snap.get("confirmed_gaps") or [])
    # some skill of the injected L3 G (G itself or any of its L4) is a confirmed gap in the session
    confirmed_gap_is_G = (any(l3_of(nodes, c_) == gap for c_ in confirmed) if gap else None)
    ds_items = int(snap.get("deep_scan_items_total") or 0)
    budget = int(ctx["ss"].settings.deep_scan_session_budget)
    max_items = int(ctx["ss"].settings.max_items)
    return {
        "i": i, "theta": theta, "gap": gap, "theta_hat": th_hat, "se": se,
        "cat_true": cls_true["category"], "cat_hat": cls_hat["category"],
        "status_true": cls_true["status"], "status_hat": cls_hat["status"],
        "items": int(db.items_answered), "ds_items": int(snap.get("deep_scan_items_total") or 0),
        "covered_all": bool(sections) and sections <= set(snap.get("covered_section_ids") or []),
        "stop": db.stop_reason, "n_chains": len(chains), "detected": detected,
        "cause": cause, "named": named,
        "ds_descents": sorted({f"{l3_of(nodes, a_.deep_scan_origin_skill_id or '') or '?'}>{l3_of(nodes, a_.skill_id or '') or '?'}"
                               for a_ in rows if a_.is_deep_scan}),
        "ds_origin_l3": sorted({l3_of(nodes, a_.deep_scan_origin_skill_id or "") or "?" for a_ in rows if a_.is_deep_scan}), "fp": fp, "key_mismatch": mismatches,
        "weak_entries": entries, "coh_entries": coh_entries, "weak_sessions": int(entries > 0),
        "coh_sessions": int(entries > 0 and coh_entries == entries), "gap_topic_named": gap_topic_named,
        "confirmed_gaps": confirmed, "confirmed_gap_is_G": confirmed_gap_is_G,
        "ds_unconfirmed": len(snap.get("deep_scan_unconfirmed") or []),   # probed skills whose gap was not confirmed
        "scan_triggered": ds_items > 0,                              # >=1 Deep Scan item was served
        "ds_budget_exhausted": ds_items >= budget,                   # session Deep Scan budget spent
        "hit_max_items": db.stop_reason == "max_items_reached" or int(db.items_answered) >= max_items,
    }


def _seed_pg(ctx, seed: int, i: int) -> None:
    """Seed the content-db RANDOM() on the (single, reused) pooled connection."""
    from sqlalchemy import text
    engine = ctx["parked"]["src.core.database"]._get_engine()   # content-service's engine
    with engine.connect() as c:
        c.execute(text("select setseed(:x)"), {"x": _u(seed, i, "pg") * 2 - 1})


# ─────────────────────────────────────────────────────────────────────────────
# Worker pool
# ─────────────────────────────────────────────────────────────────────────────
def _worker(args):
    (db_url, truth_url, content_dir, extra, idxs, seed, grade, gap_list, gap_fraction, gap_fail_p, depth) = args
    import logging
    import traceback
    # Every failure leaves the worker as a plain RuntimeError: some exceptions
    # (httpx.HTTPStatusError) cannot be unpickled in the parent, which kills Pool's
    # result thread and hangs the run forever.  Building the message is guarded too.
    try:
        ctx = bootstrap(db_url, truth_url, Path(content_dir), extra)
        logging.disable(logging.WARNING)
        fail_cache: Dict[str, set] = ctx.setdefault("_fail_cache", {})
        settings_used = _effective_settings(ctx, extra)
    except Exception as e:
        raise RuntimeError(f"worker bootstrap failed (grade {grade}, seed {seed}): {_error_detail(e)}\n"
                           f"{traceback.format_exc()[-1500:]}") from None
    out = []
    for i in idxs:
        try:
            out.append(simulate_student(ctx, i, seed, grade, gap_list, gap_fraction, gap_fail_p, fail_cache, depth))
        except Exception as e:
            raise RuntimeError(f"student {i} (grade {grade}, seed {seed}): {_error_detail(e)}\n"
                               f"{traceback.format_exc()[-1500:]}") from None
    return out, settings_used


def _error_detail(e: BaseException) -> str:
    """repr(e), plus the HTTP request/response when e carries one.  Never raises: if reading
    the response fails, repr(e) alone is still reported."""
    try:
        detail = repr(e)
    except Exception:
        detail = f"<unrepresentable {type(e).__name__}>"
    try:
        resp = getattr(e, "response", None)
        if resp is not None:
            detail += f" | {resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text[:300]}"
    except Exception as inner:
        detail += f" | (response details unavailable: {inner!r})"
    return detail


def _effective_settings(ctx, extra) -> Dict[str, Any]:
    """Settings as the worker's diagnostic-service Settings object actually holds them
    (PROD_SETTINGS + --setting overrides + every overridden key), not what the parent env says."""
    st = ctx["settings"]
    # The Deep Scan variant flags are always reported: their defaults (variant OC15) are not pinned
    # in PROD_SETTINGS, so a run without --setting must still show which values it actually used.
    keys = list(PROD_SETTINGS) + [k for k in VARIANT_FLAGS if k not in PROD_SETTINGS]
    keys += [k.upper() for k in dict(extra) if k.upper() not in keys]
    return {k: getattr(st, k.lower(), "<unknown setting>") for k in keys}


def run_arm(label: str, db_url: str, truth_url: Optional[str], a) -> List[Dict[str, Any]]:
    import multiprocessing as mp
    gap_list = a.gap_l3 if a.gap_l3 is not None else DEFAULT_GAP_L3.get(a.grade, [])
    chunk = max(1, min(25, a.n_students // (a.workers * 4) or 1))
    jobs = [(db_url, truth_url, str(a.content_service_dir), dict(a.setting), list(range(s, min(s + chunk, a.n_students))),
             a.seed, a.grade, gap_list, a.gap_fraction, a.gap_fail_p, a.dependant_depth)
            for s in range(0, a.n_students, chunk)]
    t0, res = time.time(), []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for k, (part, eff) in enumerate(pool.imap_unordered(_worker, jobs), 1):
            res.extend(part)
            EFFECTIVE_SETTINGS.setdefault(label, eff)
            if EFFECTIVE_SETTINGS[label] != eff:
                raise RuntimeError(f"workers disagree on settings: {EFFECTIVE_SETTINGS[label]} vs {eff}")
            if k % 10 == 0 or k == len(jobs):
                print(f"  [{label}] {len(res)}/{a.n_students} students, {time.time() - t0:.0f}s", flush=True)
    res.sort(key=lambda r: r["i"])
    return res


# ─────────────────────────────────────────────────────────────────────────────
# Metrics + paired bootstrap
# ─────────────────────────────────────────────────────────────────────────────
def _arr(recs, key, dtype=float):
    return np.array([r[key] for r in recs], dtype=dtype)


def _flag(recs, key, fallback=None) -> np.ndarray:
    """0/1 array of a boolean per-student field (None -> 0); fallback(r) for records of older runs."""
    def one(r):
        v = r.get(key)
        if v is None and fallback is not None:
            v = fallback(r)
        return 1.0 if v else 0.0
    return np.array([one(r) for r in recs], float)


def per_student_matrix(recs) -> Dict[str, np.ndarray]:
    return {
        # Stage-0 root-cause metrics (older result files lack some fields; derived where possible)
        "gap_topic_named": _flag(recs, "gap_topic_named"),
        "confirmed_gap_is_G": _flag(recs, "confirmed_gap_is_G"),
        "scan_triggered": _flag(recs, "scan_triggered", lambda r: r["ds_items"] > 0),
        "ds_budget_exhausted": _flag(recs, "ds_budget_exhausted"),
        "hit_max_items": _flag(recs, "hit_max_items", lambda r: r["stop"] == "max_items_reached"),
        "acc_cat": np.array([r["cat_true"] == r["cat_hat"] for r in recs], float),
        "acc_status": np.array([r["status_true"] == r["status_hat"] for r in recs], float),
        "sq_err": (_arr(recs, "theta_hat") - _arr(recs, "theta")) ** 2,
        "err": _arr(recs, "theta_hat") - _arr(recs, "theta"),
        "items": _arr(recs, "items"), "ds_items": _arr(recs, "ds_items"),
        "covered_all": _arr(recs, "covered_all", float),
        "has_gap": np.array([r["gap"] is not None for r in recs]),
        "detected": _arr(recs, "detected", float), "cause": _arr(recs, "cause", float),
        "named": _arr(recs, "named", float),
        "fp": _arr(recs, "fp", float),
        "weak_entries": _arr(recs, "weak_entries"), "coh_entries": _arr(recs, "coh_entries"),
        "weak_sessions": _arr(recs, "weak_sessions"), "coh_sessions": _arr(recs, "coh_sessions"),
    }


def summarize(recs) -> Dict[str, Any]:
    m = per_student_matrix(recs)
    g = m["has_gap"]
    stops: Dict[str, int] = {}
    for r in recs:
        stops[r["stop"]] = stops.get(r["stop"], 0) + 1
    return {
        "n": len(recs), "n_gap": int(g.sum()),
        "acc_category": m["acc_cat"].mean(),
        "acc_category_gap": m["acc_cat"][g].mean() if g.any() else None,
        "acc_category_nogap": m["acc_cat"][~g].mean() if (~g).any() else None,
        "detect_by_gap": {
            k: {**{t: float(np.mean([r[t] for r in recs if r["gap"] == k])) for t in ("detected", "cause", "named")},
                **{t: float(np.mean([bool(r.get(t)) for r in recs if r["gap"] == k]))
                   for t in ("gap_topic_named", "confirmed_gap_is_G", "scan_triggered")},
                "n": sum(1 for r in recs if r["gap"] == k)}
            for k in sorted({r["gap"] for r in recs if r["gap"]})},
        "acc_status5": m["acc_status"].mean(),
        "rmse_theta": math.sqrt(m["sq_err"].mean()), "bias_theta": m["err"].mean(),
        "len_mean": m["items"].mean(), "len_p90": float(np.percentile(m["items"], 90)),
        "covered_all_pct": 100 * m["covered_all"].mean(),
        "deep_scan_items_mean": m["ds_items"].mean(),
        "deep_scan_any_pct": 100 * (m["ds_items"] > 0).mean(),
        "detect_root": m["detected"][g].mean() if g.any() else None,
        "detect_cause": m["cause"][g].mean() if g.any() else None,
        "detect_named": m["named"][g].mean() if g.any() else None,
        "bg_chain_nogap": m["fp"][~g].mean() if (~g).any() else None,
        # stage-0 metrics: gap_topic_named = report names the gap L3's L2 topic (gap students);
        # confirmed_gap_is_G = a skill of the gap L3 is in confirmed_gaps (gap students);
        # fp_nogap = gap-free students whose chain root lies in the candidate gap-L3 set (cf. detect_*)
        "gap_topic_named": m["gap_topic_named"][g].mean() if g.any() else None,
        "confirmed_gap_is_G": m["confirmed_gap_is_G"][g].mean() if g.any() else None,
        "fp_nogap": m["fp"][~g].mean() if (~g).any() else None,
        "scan_triggered_gap": m["scan_triggered"][g].mean() if g.any() else None,
        "scan_triggered_nogap": m["scan_triggered"][~g].mean() if (~g).any() else None,
        "ds_items_mean_gap": m["ds_items"][g].mean() if g.any() else None,
        "ds_items_mean_nogap": m["ds_items"][~g].mean() if (~g).any() else None,
        "ds_items_mean_if_triggered": (m["ds_items"][m["scan_triggered"] > 0].mean()
                                       if (m["scan_triggered"] > 0).any() else None),
        "ds_budget_exhausted": m["ds_budget_exhausted"].mean(),
        "ds_budget_exhausted_gap": m["ds_budget_exhausted"][g].mean() if g.any() else None,
        "hit_max_items": m["hit_max_items"].mean(),
        "coherent_session_share": float(m["coh_sessions"].sum() / max(1, m["weak_sessions"].sum())),
        "coherent_entry_share": float(m["coh_entries"].sum() / max(1, m["weak_entries"].sum())),
        "sessions_with_weak_pct": 100 * float(m["weak_sessions"].mean()),
        "weak_entries_per_session": float(m["weak_entries"].mean()),
        "key_mismatch_items": int(sum(r["key_mismatch"] for r in recs)),
        "stop_reasons": stops,
    }


def paired_bootstrap(ra, rb, n_boot=2000, seed=12345) -> Dict[str, Any]:
    """B - A with 95% percentile CI, resampling students (same index in both arms)."""
    assert [r["i"] for r in ra] == [r["i"] for r in rb]
    A, B = per_student_matrix(ra), per_student_matrix(rb)
    new_fields = all("ds_budget_exhausted" in r and "confirmed_gap_is_G" in r for r in (ra[0], rb[0]))
    n = len(ra)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, (n_boot, n))
    g = A["has_gap"]
    assert (g == B["has_gap"]).all(), "arms must share the same gap assignment"
    gi = np.flatnonzero(g)
    gidx = gi[rng.integers(0, len(gi), (n_boot, len(gi)))] if len(gi) else None
    ngi = np.flatnonzero(~g)
    nidx = ngi[rng.integers(0, len(ngi), (n_boot, len(ngi)))] if len(ngi) else None

    def ci(d):
        lo, hi = np.percentile(d, [2.5, 97.5])
        return [float(lo), float(hi)]

    out = {}

    def mean_metric(name, key, pop=None, boot=None, scale=1.0):
        """pop: indices of the population (None = all); boot: resampled indices of it."""
        a_, b_ = A[key], B[key]
        if pop is None:
            pop, boot = slice(None), idx
        d = (b_[boot].mean(1) - a_[boot].mean(1)) * scale
        lo, hi = ci(d)
        out[name] = {"A": float(a_[pop].mean() * scale), "B": float(b_[pop].mean() * scale),
                     "diff": float((b_[pop].mean() - a_[pop].mean()) * scale), "ci95": [lo, hi],
                     "excludes_0": bool(lo > 0 or hi < 0)}

    mean_metric("acc_category", "acc_cat")
    mean_metric("acc_status5", "acc_status")
    if gidx is not None:
        mean_metric("acc_category_gapstudents", "acc_cat", gi, gidx)
    if nidx is not None:
        mean_metric("acc_category_nogap", "acc_cat", ngi, nidx)
    mean_metric("len_mean", "items")
    mean_metric("deep_scan_items", "ds_items")
    mean_metric("covered_all_pct", "covered_all", scale=100)
    if gidx is not None:
        mean_metric("detect_root", "detected", gi, gidx)
        mean_metric("detect_cause", "cause", gi, gidx)
        mean_metric("detect_named", "named", gi, gidx)
        mean_metric("gap_topic_named", "gap_topic_named", gi, gidx)
        mean_metric("ds_items_gap", "ds_items", gi, gidx)
        if new_fields:
            mean_metric("confirmed_gap_is_G", "confirmed_gap_is_G", gi, gidx)
            mean_metric("scan_triggered_gap", "scan_triggered", gi, gidx)
            mean_metric("ds_budget_exhausted_gap", "ds_budget_exhausted", gi, gidx)
    if nidx is not None:
        mean_metric("bg_chain_nogap", "fp", ngi, nidx)
        mean_metric("fp_nogap", "fp", ngi, nidx)
        mean_metric("scan_triggered_nogap", "scan_triggered", ngi, nidx)
        mean_metric("ds_items_nogap", "ds_items", ngi, nidx)
    if new_fields:      # fields recorded only by runs made after the stage-0 change
        mean_metric("ds_budget_exhausted", "ds_budget_exhausted")
        mean_metric("hit_max_items", "hit_max_items")
    for name, num, den in (("coherent_session_share", "coh_sessions", "weak_sessions"),
                           ("coherent_entry_share", "coh_entries", "weak_entries")):
        ra_, rb_ = A[num].sum() / max(1, A[den].sum()), B[num].sum() / max(1, B[den].sum())
        d = (B[num][idx].sum(1) / np.maximum(1, B[den][idx].sum(1))
             - A[num][idx].sum(1) / np.maximum(1, A[den][idx].sum(1)))
        out[name] = {"A": float(ra_), "B": float(rb_), "diff": float(rb_ - ra_), "ci95": ci(d)}
    # RMSE and p90 are not means: resample explicitly
    ra_, rb_ = A["sq_err"], B["sq_err"]
    d = np.sqrt(rb_[idx].mean(1)) - np.sqrt(ra_[idx].mean(1))
    out["rmse_theta"] = {"A": float(np.sqrt(ra_.mean())), "B": float(np.sqrt(rb_.mean())),
                         "diff": float(np.sqrt(rb_.mean()) - np.sqrt(ra_.mean())), "ci95": ci(d)}
    d = np.percentile(B["items"][idx], 90, axis=1) - np.percentile(A["items"][idx], 90, axis=1)
    out["len_p90"] = {"A": float(np.percentile(A["items"], 90)), "B": float(np.percentile(B["items"], 90)),
                      "diff": float(np.percentile(B["items"], 90) - np.percentile(A["items"], 90)), "ci95": ci(d)}
    return out


def print_summary(label: str, s: Dict[str, Any]) -> None:
    f = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
    print(f"[{label}] n={s['n']} (gap={s['n_gap']}) acc3={f(s['acc_category'])} acc5={f(s['acc_status5'])} "
          f"rmse={f(s['rmse_theta'])} bias={f(s['bias_theta'])} len={f(s['len_mean'],2)}/p90={f(s['len_p90'],0)} "
          f"cover={f(s['covered_all_pct'],1)}% ds={f(s['deep_scan_items_mean'],2)} "
          f"detect={f(s['detect_root'])} cause={f(s['detect_cause'])} named={f(s['detect_named'])} fp={f(s['fp_nogap'])} "
          f"topic_named={f(s['gap_topic_named'])} conf_is_G={f(s['confirmed_gap_is_G'])} "
          f"scan(gap/nogap)={f(s['scan_triggered_gap'],2)}/{f(s['scan_triggered_nogap'],2)} "
          f"budget_exh={f(s['ds_budget_exhausted'],2)} max_items={f(s['hit_max_items'],2)} "
          f"coh_sess={s['coherent_session_share']:.3f} coh_entry={s['coherent_entry_share']:.3f} "
          f"keymis={s['key_mismatch_items']} stops={s['stop_reasons']}")


def print_paired(p: Dict[str, Any]) -> None:
    for k, v in p.items():
        print(f"  {k:18s} A={v['A']:.4f} B={v['B']:.4f} diff={v['diff']:+.4f} CI95=[{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}]")


# ─────────────────────────────────────────────────────────────────────────────
# Scratch DB for A/B
# ─────────────────────────────────────────────────────────────────────────────
def _swap_db(url: str, name: str) -> str:
    return url.rsplit("/", 1)[0] + "/" + name


def make_scratch(url: str, name: str, edges: Optional[List[dict]] = None) -> int:
    """Copy the content DB (CREATE DATABASE ... TEMPLATE) and optionally insert prerequisite edges."""
    import psycopg2
    src = url.rsplit("/", 1)[1].split("?")[0]
    conn = psycopg2.connect(_swap_db(url, "postgres"))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
    cur.execute(f'CREATE DATABASE "{name}" TEMPLATE "{src}"')
    conn.close()
    added = 0
    c2 = psycopg2.connect(_swap_db(url, name))
    cur = c2.cursor()
    for e in edges or []:
        cur.execute(
            "insert into skill_prerequisites (skill_id, prerequisite_id, weight, dependency_type, criticality,"
            " relationship_description, discovery_source) values (%s,%s,%s,%s,%s,%s,%s)"
            " on conflict (skill_id, prerequisite_id) do nothing",
            (e["skill_id"], e["prerequisite_id"], e.get("weight", 1.0), e.get("dependency_type", "hard"),
             e.get("criticality", 5), e.get("relationship_description"), e.get("discovery_source", "expert")))
        added += cur.rowcount
    c2.commit(); c2.close()
    return added


def apply_manifest(scratch_url: str, manifest: str, content_dir: Path, backup: str, ack_protected: bool) -> str:
    """Run content-service's real guarded_repair tool (--execute) on the SCRATCH db only."""
    import subprocess
    if scratch_url.rsplit("/", 1)[1].split("?")[0] == "algo_content":
        raise RuntimeError("refusing to apply a manifest to the live algo_content database")
    cmd = [sys.executable, "-m", "tools.content_review.guarded_repair", "--manifest", str(Path(manifest).resolve()),
           "--execute", "--backup", backup] + (["--ack-protected"] if ack_protected else [])
    env = dict(os.environ, CONTENT_REPAIR_DATABASE_URL=scratch_url)
    r = subprocess.run(cmd, cwd=str(content_dir), env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("guarded_repair failed:\n" + (r.stderr or r.stdout)[-1500:])
    return r.stdout.strip()[-400:]


def deactivate_empty_l4(scratch_url: str) -> List[str]:
    """Counterfactual: deactivate active L4s that have no active task (scratch DB only)."""
    import psycopg2
    if scratch_url.rsplit("/", 1)[1].split("?")[0] == "algo_content":
        raise RuntimeError("refusing to modify the live algo_content database")
    c = psycopg2.connect(scratch_url)
    cur = c.cursor()
    cur.execute("update knowledge_hierarchy k set is_active=false where k.level='L4' and k.is_active and not exists "
                "(select 1 from tasks_master t where t.skill_id=k.id and t.is_active) returning k.id")
    ids = sorted(r[0] for r in cur.fetchall())
    c.commit(); c.close()
    return ids


def candidate_l3(urls: List[str], grade: int) -> List[str]:
    """Active G<grade> L3s that have active tasks in EVERY given db."""
    from sqlalchemy import create_engine, text
    sets = []
    for u in urls:
        eng = create_engine(u)
        with eng.connect() as c:
            sets.append({r[0] for r in c.execute(text(
                "select l3.id from knowledge_hierarchy l3 where l3.level='L3' and l3.is_active and l3.id like :p "
                "and exists (select 1 from knowledge_hierarchy l4 join tasks_master t on t.skill_id=l4.id and t.is_active "
                "where l4.parent_id=l3.id and l4.is_active)"), {"p": f"G{grade}\\_%"})})
        eng.dispose()
    return sorted(set.intersection(*sets))


def drop_scratch(url: str, name: str) -> None:
    import psycopg2
    conn = psycopg2.connect(_swap_db(url, "postgres"))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("select pg_terminate_backend(pid) from pg_stat_activity where datname=%s and pid<>pg_backend_pid()", (name,))
    cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
    conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--grade", type=int, default=11)
    ap.add_argument("--n-students", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--content-db-url", help="postgresql://user:pw@host:port/db (arm A)")
    ap.add_argument("--truth-db-url", help="graph used to define gap dependants (default: content db)")
    ap.add_argument("--add-edges", help="JSON with key 'prerequisites': run arm B on a scratch DB copy + these edges")
    ap.add_argument("--apply-manifest", help="content_repairs manifest applied to the scratch copy with the real "
                    "tools.content_review.guarded_repair (--execute); combinable with --add-edges")
    ap.add_argument("--backup-path", default="/tmp/cat_sim_manifest_backup.json", help="backup file for guarded_repair")
    ap.add_argument("--deactivate-empty-l4", action="store_true",
                    help="counterfactual on the scratch copy: deactivate active L4 skills left without active tasks")
    ap.add_argument("--ack-protected", action="store_true", help="pass through to guarded_repair")
    ap.add_argument("--scratch-db", default="algo_content_sim")
    ap.add_argument("--gap-l3", nargs="*", default=None, help="L3 ids to inject (default: G11 derivative/integral set)")
    ap.add_argument("--gap-fraction", type=float, default=0.5)
    ap.add_argument("--gap-fail-p", type=float, default=0.85)
    ap.add_argument("--dependant-depth", type=int, default=1,
                    help="hops of truth-graph dependants that also fail with the gap (1 = direct, 0 = transitive closure)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--setting", action="append", default=[], type=lambda s: tuple(s.split("=", 1)),
                    help="override a diagnostic setting, e.g. MAX_ITEMS=30")
    ap.add_argument("--content-service-dir", type=Path, default=DEFAULT_CONTENT_DIR)
    ap.add_argument("--out", help="write raw per-student results + summaries as JSON")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"))
    a = ap.parse_args()

    if a.compare:
        def students(path):
            arms_ = json.load(open(path))["arms"]
            return arms_.get("A", next(iter(arms_.values())))["students"]
        print_paired(paired_bootstrap(students(a.compare[0]), students(a.compare[1]), a.n_boot))
        return
    if not a.content_db_url:
        ap.error("--content-db-url is required")

    arms: Dict[str, Any] = {}
    out: Dict[str, Any] = {"args": {k: str(v) for k, v in vars(a).items() if k != "content_db_url"},
                           "settings": None, "arms": arms}
    scratch_url = None
    try:
        truth = a.truth_db_url
        if a.add_edges or a.apply_manifest:
            edges = json.load(open(a.add_edges))["prerequisites"] if a.add_edges else []
            scratch_url = _swap_db(a.content_db_url, a.scratch_db)
            added = make_scratch(a.content_db_url, a.scratch_db, edges)
            truth = truth or scratch_url
            if a.add_edges:
                out["edges_in_file"], out["edges_inserted"] = len(edges), added
                print(f"scratch DB {a.scratch_db}: {added}/{len(edges)} edges inserted", flush=True)
            if a.apply_manifest:
                out["manifest_result"] = apply_manifest(scratch_url, a.apply_manifest, a.content_service_dir,
                                                        a.backup_path, a.ack_protected)
                print("manifest applied on scratch:", out["manifest_result"][-200:], flush=True)
        if a.deactivate_empty_l4 and scratch_url:
            out["deactivated_empty_l4"] = deactivate_empty_l4(scratch_url)
            print("scratch: deactivated empty L4:", out["deactivated_empty_l4"], flush=True)
        if a.gap_l3 == ["auto"]:
            a.gap_l3 = candidate_l3([a.content_db_url] + ([scratch_url] if scratch_url else []), a.grade)
            out["gap_l3_auto"] = a.gap_l3
            print(f"gap L3 candidates (tasks in all arms): {len(a.gap_l3)}", flush=True)
        for label, url in (("A", a.content_db_url),) + ((("B", scratch_url),) if scratch_url else ()):
            recs = run_arm(label, url, truth, a)
            arms[label] = {"summary": summarize(recs), "students": recs, "settings": EFFECTIVE_SETTINGS.get(label)}
            out["settings"] = EFFECTIVE_SETTINGS.get(label)        # effective, as read back from the workers
            print_summary(label, arms[label]["summary"])
        if "B" in arms:
            out["paired_bootstrap_B_minus_A"] = paired_bootstrap(arms["A"]["students"], arms["B"]["students"], a.n_boot)
            print("paired bootstrap B - A:")
            print_paired(out["paired_bootstrap_B_minus_A"])
    finally:
        if scratch_url:
            drop_scratch(a.content_db_url, a.scratch_db)
            print(f"scratch DB {a.scratch_db} dropped", flush=True)
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(out, fh, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
        print("raw results ->", a.out)


if __name__ == "__main__":
    main()
