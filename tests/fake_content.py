"""A counting stand-in for the content-service read API (WC-B P-01..P-03): the same routes diagnostic-service calls, answered from memory.

``FakeContent.get`` replaces ``content_client.get`` (and ``post`` the avg-difficulty call); ``calls`` is the list of requests, so a test can say how
many HTTP calls one answer of a student or one teacher's report costs.  ``/tasks`` orders like the real endpoint: nearest to ``target_b`` first (random
among equals), else by irt_difficulty, after the filters skill / exclude / is_active, then LIMIT.
"""
from __future__ import annotations

import json
import random
import types
from collections import Counter
from typing import Optional


class Response:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def node(node_id, parent, level, grade, order=0):
    return {"id": node_id, "parent_id": parent, "level": level, "name": f"name {node_id}", "name_ru": f"имя {node_id}",
            "class_level_start": grade, "sequence_order": order}


class FakeContent:
    def __init__(self, *, grades=(7,), topics=2, subtopics_per_topic=3, skills_per_subtopic=2):
        self.nodes: dict[str, dict] = {}
        self.prereqs: dict[str, list] = {}
        self.tasks: dict[str, list] = {}           # skill_id -> [task dict]
        self.calls: list[tuple[str, dict]] = []
        self.down = False
        self.task_rows = 0       # rows and JSON bytes that GET /tasks returned (what the content DB sorts and diag parses)
        self.task_bytes = 0
        for g in grades:
            sec = f"G{g}_L1"
            self.nodes[sec] = node(sec, None, "L1", g)
            for t in range(topics):
                tid = f"G{g}_T{t}"
                self.nodes[tid] = node(tid, sec, "L2", g, t)
                for s in range(subtopics_per_topic):
                    sid = f"{tid}_S{s}"
                    self.nodes[sid] = node(sid, tid, "L3", g, s)
                    for k in range(skills_per_subtopic):
                        kid = f"{sid}_K{k}"
                        self.nodes[kid] = node(kid, sid, "L4", g, k)

    # ── data helpers ──
    def l4(self, grade):
        return [n["id"] for n in self.nodes.values() if n["level"] == "L4" and n["class_level_start"] == grade]

    def add_tasks(self, skill_id, difficulties, *, prefix=None):
        prefix = prefix or skill_id
        self.tasks.setdefault(skill_id, []).extend(
            {"id": f"{prefix}_t{i}", "skill_id": skill_id, "irt_difficulty": b, "difficulty": "B", "question_text": "q", "answer_type": "numeric"}
            for i, b in enumerate(difficulties))

    # ── transport ──
    def count(self, prefix="") -> int:
        return sum(1 for path, _ in self.calls if path.startswith(prefix))

    def kinds(self) -> Counter:
        return Counter(("tasks" if p.endswith("/tasks") else "skills-list" if p.endswith("/skills") else p.rsplit("/", 1)[-1] if p.endswith(("/children", "/prerequisites")) else "node")
                       for p, _ in self.calls)

    def get(self, path, **kwargs):
        params = kwargs.get("params") or {}
        self.calls.append((path, params))
        if self.down:
            raise ConnectionError("content-service is down")
        base = "/api/v1/content"
        assert path.startswith(base), path
        rest = path[len(base):]
        if rest == "/skills":
            return Response([n for n in self.nodes.values() if n["level"] == params["level"] and n["class_level_start"] == params["grade"]])
        if rest == "/tasks":
            rows = self._list_tasks(params)
            self.task_rows += len(rows)
            self.task_bytes += len(json.dumps(rows))
            return Response(rows)
        parts = rest.strip("/").split("/")
        assert parts[0] == "skills", path
        node_id = parts[1]
        if len(parts) == 2:
            return Response(self.nodes[node_id]) if node_id in self.nodes else Response({"detail": "not found"}, 404)
        if parts[2] == "children":
            return Response(sorted((n for n in self.nodes.values() if n["parent_id"] == node_id), key=lambda n: n["sequence_order"]))
        if parts[2] == "prerequisites":
            return Response(self.prereqs.get(node_id, []))
        raise AssertionError(path)

    def post(self, path, **kwargs):
        self.calls.append((path, kwargs.get("json") or {}))
        assert path.endswith("/tasks/avg-difficulty")
        out = {}
        for sid in kwargs["json"]["skill_ids"]:
            bs = [t["irt_difficulty"] for t in self.tasks.get(sid, [])]
            if bs:
                out[sid] = sum(bs) / len(bs)
        return Response(out)

    def _list_tasks(self, params):
        skills = params.get("skill_ids") or ([params["skill_id"]] if params.get("skill_id") else [])
        exclude = set(params.get("exclude_ids") or [])
        rows = [t for sid in skills for t in self.tasks.get(sid, []) if t["id"] not in exclude]
        target: Optional[float] = params.get("target_b")
        rng = random.random
        if target is not None:
            rows.sort(key=lambda t: (abs(t["irt_difficulty"] - target), rng()))
        else:
            rows.sort(key=lambda t: t["irt_difficulty"])
        return rows[: int(params.get("limit", 20))]

    def patch(self, monkeypatch):
        from src.repositories import knowledge_repo

        monkeypatch.setattr(knowledge_repo.content_client, "get", self.get)
        monkeypatch.setattr(knowledge_repo.content_client, "post", self.post)
        return self
