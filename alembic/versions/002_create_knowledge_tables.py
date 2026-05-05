"""Create knowledge base tables and seed Grade 5 test data

Revision ID: 002_knowledge_tables
Revises: 001_diag_tables
Create Date: 2026-05-05

Creates the three shared-knowledge tables that the diagnostic service reads from:
  knowledge_hierarchy   — L1–L4 curriculum skill tree
  skill_prerequisites   — prerequisite graph edges
  tasks_master          — task bank with IRT parameters

Seeds Grade 5 test data:
  L1 sections  : G5_NAT, G5_FRAC
  L2 topics    : G5_T01–G5_T10  (match grade_topic_map seed in 001)
  L3 subtopics : 2 per topic  → 20 nodes
  L4 skills    : 2 per subtopic → 40 nodes
  Tasks        : 3 per skill (b = -1.5, 0.0, +1.5) → 120 tasks
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_knowledge_tables"
down_revision = "001_diag_tables"
branch_labels = ("standalone",)
depends_on = None


# ── helpers ────────────────────────────────────────────────────────────────

def _kh(id_, level, parent_id, name_ru, importance=5, seq=0, cl_start=5, cl_end=11):
    return {
        "id": id_, "level": level, "parent_id": parent_id,
        "name": name_ru, "name_ru": name_ru, "description": None,
        "class_level_start": cl_start, "class_level_end": cl_end,
        "importance": importance, "sequence_order": seq,
        "cognitive_type": "apply", "is_active": True,
    }


def _task(id_, skill_id, q_text, correct, b_param, a_param=1.0, c_param=0.0,
          answer_type="open", answer_options=None, distractor_meta=None):
    return {
        "id": id_, "skill_id": skill_id,
        "question_text": q_text, "question_latex": None,
        "answer_type": answer_type, "correct_answer": correct,
        "answer_options": answer_options,
        "difficulty": "A" if b_param < -0.5 else ("C" if b_param > 0.5 else "B"),
        "irt_discrimination": a_param,
        "irt_difficulty": b_param,
        "irt_guessing": c_param,
        "solution_steps": None,
        "hints": None,
        "distractor_meta": distractor_meta,
        "is_active": True,
    }


# ── curriculum data ────────────────────────────────────────────────────────

def _build_hierarchy():
    rows = []

    # L1 sections
    rows.append(_kh("G5_NAT",  "L1", None, "Натуральные числа",   importance=8, seq=0))
    rows.append(_kh("G5_FRAC", "L1", None, "Дроби и десятичные",  importance=9, seq=1))

    # L2 topics — must match grade_topic_map seeded in migration 001
    topics = [
        ("G5_T01", "G5_NAT",  "Чтение и запись натуральных чисел",   6, 0),
        ("G5_T02", "G5_NAT",  "Сложение и вычитание",                 7, 1),
        ("G5_T03", "G5_NAT",  "Умножение и деление",                  9, 2),
        ("G5_T04", "G5_NAT",  "Степени натуральных чисел",            5, 3),
        ("G5_T05", "G5_NAT",  "НОД и НОК",                           6, 4),
        ("G5_T06", "G5_FRAC", "Обыкновенные дроби",                  9, 0),
        ("G5_T07", "G5_FRAC", "Сложение и вычитание дробей",         8, 1),
        ("G5_T08", "G5_FRAC", "Умножение и деление дробей",          8, 2),
        ("G5_T09", "G5_FRAC", "Десятичные дроби",                    5, 3),
        ("G5_T10", "G5_FRAC", "Смешанные числа",                     6, 4),
    ]
    for tid, parent, name, imp, seq in topics:
        rows.append(_kh(tid, "L2", parent, name, importance=imp, seq=seq))

    # L3 subtopics and L4 skills
    subtopic_defs = {
        "G5_T01": [("Запись числа", 0), ("Сравнение чисел", 1)],
        "G5_T02": [("Сложение натуральных чисел", 0), ("Вычитание натуральных чисел", 1)],
        "G5_T03": [("Умножение натуральных чисел", 0), ("Деление натуральных чисел", 1)],
        "G5_T04": [("Возведение в степень", 0), ("Квадрат и куб числа", 1)],
        "G5_T05": [("Наибольший общий делитель", 0), ("Наименьшее общее кратное", 1)],
        "G5_T06": [("Понятие дроби", 0), ("Правильные и неправильные дроби", 1)],
        "G5_T07": [("Сложение дробей с одинаковым знаменателем", 0), ("Сложение дробей с разным знаменателем", 1)],
        "G5_T08": [("Умножение дроби на натуральное число", 0), ("Умножение дроби на дробь", 1)],
        "G5_T09": [("Чтение и запись десятичных дробей", 0), ("Сложение десятичных дробей", 1)],
        "G5_T10": [("Перевод в неправильную дробь", 0), ("Действия со смешанными числами", 1)],
    }

    skill_defs = {
        # topic_id → subtopic_idx → list of (skill_name, seq)
    }

    for topic_id, subs in subtopic_defs.items():
        for s_idx, (s_name, s_seq) in enumerate(subs):
            sub_id = f"{topic_id}_S{s_idx + 1}"
            rows.append(_kh(sub_id, "L3", topic_id, s_name, seq=s_seq))
            # 2 skills per subtopic
            skill_names = [
                f"Базовый: {s_name}",
                f"Применение: {s_name}",
            ]
            for k_idx, k_name in enumerate(skill_names):
                skill_id = f"{sub_id}_K{k_idx + 1}"
                rows.append(_kh(skill_id, "L4", sub_id, k_name, seq=k_idx))

    return rows


def _build_tasks():
    """Generate 3 tasks per L4 skill at b = -1.5, 0.0, +1.5."""
    rows = []

    # topic_id → subtopic_count (always 2), skill_count per sub (always 2)
    topics = [
        "G5_T01", "G5_T02", "G5_T03", "G5_T04", "G5_T05",
        "G5_T06", "G5_T07", "G5_T08", "G5_T09", "G5_T10",
    ]

    # Prebuilt task templates per topic (question, answer, b levels)
    templates = {
        "G5_T01": [
            ("Запишите цифрами число: сто двадцать три", "123"),
            ("Запишите цифрами число: четыре тысячи пятьдесят шесть", "4056"),
            ("Запишите цифрами число: миллион двести тысяч семьдесят пять", "1200075"),
        ],
        "G5_T02": [
            ("Вычислите: 45 + 38 = ?", "83"),
            ("Вычислите: 374 + 256 = ?", "630"),
            ("Вычислите: 5 483 + 2 917 = ?", "8400"),
        ],
        "G5_T03": [
            ("Вычислите: 6 × 7 = ?", "42"),
            ("Вычислите: 48 ÷ 6 = ?", "8"),
            ("Вычислите: 144 ÷ 12 = ?", "12"),
        ],
        "G5_T04": [
            ("Вычислите: 3² = ?", "9"),
            ("Вычислите: 4³ = ?", "64"),
            ("Вычислите: 2⁵ = ?", "32"),
        ],
        "G5_T05": [
            ("Найдите НОД(12, 8) = ?", "4"),
            ("Найдите НОК(4, 6) = ?", "12"),
            ("Найдите НОД(36, 48) = ?", "12"),
        ],
        "G5_T06": [
            ("Какая часть закрашена, если 2 из 4 равных частей закрашены?", "1/2"),
            ("Запишите дробь: три седьмых", "3/7"),
            ("Сравните дроби: 3/5 и 4/7. Какая больше? Введите её (3/5 или 4/7)", "3/5"),
        ],
        "G5_T07": [
            ("Вычислите: 1/5 + 2/5 = ?", "3/5"),
            ("Вычислите: 1/3 + 1/4 = ?", "7/12"),
            ("Вычислите: 5/6 + 3/8 = ?", "29/24"),
        ],
        "G5_T08": [
            ("Вычислите: 2/3 × 3 = ?", "2"),
            ("Вычислите: 2/3 × 3/4 = ?", "1/2"),
            ("Вычислите: 5/6 × 12/25 = ?", "2/5"),
        ],
        "G5_T09": [
            ("Запишите цифрами: ноль целых пять десятых", "0.5"),
            ("Вычислите: 1.2 + 0.8 = ?", "2"),
            ("Вычислите: 3.75 + 1.25 = ?", "5"),
        ],
        "G5_T10": [
            ("Запишите как неправильную дробь: 1 целая 2/3", "5/3"),
            ("Вычислите: 1½ + 2½ = ?", "4"),
            ("Вычислите: 3⅓ - 1⅔ = ?", "5/3"),
        ],
    }

    b_levels = [-1.5, 0.0, 1.5]

    for topic_id in topics:
        for s_idx in range(1, 3):       # S1, S2
            sub_id = f"{topic_id}_S{s_idx}"
            for k_idx in range(1, 3):   # K1, K2
                skill_id = f"{sub_id}_K{k_idx}"
                tmpl_list = templates.get(topic_id, [
                    ("Пример задания 1", "1"),
                    ("Пример задания 2", "2"),
                    ("Пример задания 3", "3"),
                ])
                for t_idx, b in enumerate(b_levels):
                    q_text, correct = tmpl_list[t_idx % len(tmpl_list)]
                    task_id = f"TSK_{skill_id}_{t_idx + 1}"
                    rows.append(_task(
                        id_=task_id,
                        skill_id=skill_id,
                        q_text=q_text,
                        correct=correct,
                        b_param=b,
                    ))
    return rows


def upgrade() -> None:
    # ── knowledge_hierarchy ────────────────────────────────────────────────
    op.create_table(
        "knowledge_hierarchy",
        sa.Column("id", sa.String(30), primary_key=True),
        sa.Column("level", sa.String(2), nullable=False),
        sa.Column("parent_id", sa.String(30), sa.ForeignKey("knowledge_hierarchy.id"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_ru", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("class_level_start", sa.Integer, nullable=True),
        sa.Column("class_level_end", sa.Integer, nullable=True),
        sa.Column("importance", sa.Integer, server_default="5"),
        sa.Column("sequence_order", sa.Integer, server_default="0"),
        sa.Column("cognitive_type", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
    )
    op.create_index("idx_kh_parent", "knowledge_hierarchy", ["parent_id"])
    op.create_index("idx_kh_level", "knowledge_hierarchy", ["level"])

    # ── skill_prerequisites ────────────────────────────────────────────────
    op.create_table(
        "skill_prerequisites",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("skill_id", sa.String(30), sa.ForeignKey("knowledge_hierarchy.id"), nullable=False, index=True),
        sa.Column("prerequisite_id", sa.String(30), sa.ForeignKey("knowledge_hierarchy.id"), nullable=False),
        sa.Column("weight", sa.Numeric(4, 2), server_default="1.0"),
        sa.Column("is_hard", sa.Boolean, server_default="true"),
    )

    # ── tasks_master ───────────────────────────────────────────────────────
    op.create_table(
        "tasks_master",
        sa.Column("id", sa.String(30), primary_key=True),
        sa.Column("skill_id", sa.String(30), sa.ForeignKey("knowledge_hierarchy.id"), nullable=True),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("question_latex", sa.Text, nullable=True),
        sa.Column("answer_type", sa.String(20), nullable=False),
        sa.Column("correct_answer", sa.Text, nullable=False),
        sa.Column("answer_options", postgresql.JSONB, nullable=True),
        sa.Column("difficulty", sa.String(1), server_default="'B'"),
        sa.Column("irt_discrimination", sa.Numeric(6, 4), server_default="1.0"),
        sa.Column("irt_difficulty", sa.Numeric(6, 4), server_default="0.0"),
        sa.Column("irt_guessing", sa.Numeric(6, 4), server_default="0.0"),
        sa.Column("solution_steps", postgresql.JSONB, nullable=True),
        sa.Column("hints", postgresql.JSONB, nullable=True),
        sa.Column("distractor_meta", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
    )
    op.create_index("idx_tm_skill", "tasks_master", ["skill_id"])

    # ── Seed data ──────────────────────────────────────────────────────────
    kh_table = sa.table(
        "knowledge_hierarchy",
        sa.column("id"), sa.column("level"), sa.column("parent_id"),
        sa.column("name"), sa.column("name_ru"), sa.column("description"),
        sa.column("class_level_start"), sa.column("class_level_end"),
        sa.column("importance"), sa.column("sequence_order"),
        sa.column("cognitive_type"), sa.column("is_active"),
    )
    op.bulk_insert(kh_table, _build_hierarchy())

    # Prerequisite sample: K2 of each subtopic requires K1 of same subtopic
    topics = [
        "G5_T01", "G5_T02", "G5_T03", "G5_T04", "G5_T05",
        "G5_T06", "G5_T07", "G5_T08", "G5_T09", "G5_T10",
    ]
    prereq_rows = []
    for topic_id in topics:
        for s_idx in range(1, 3):
            sub_id = f"{topic_id}_S{s_idx}"
            # K2 depends on K1 (hard prerequisite)
            prereq_rows.append({
                "skill_id": f"{sub_id}_K2",
                "prerequisite_id": f"{sub_id}_K1",
                "weight": "1.00",
                "is_hard": True,
            })
        # S2 of topic requires S1_K2 (soft prerequisite)
        prereq_rows.append({
            "skill_id": f"{topic_id}_S2_K1",
            "prerequisite_id": f"{topic_id}_S1_K2",
            "weight": "0.80",
            "is_hard": False,
        })

    prereq_table = sa.table(
        "skill_prerequisites",
        sa.column("skill_id"), sa.column("prerequisite_id"),
        sa.column("weight"), sa.column("is_hard"),
    )
    op.bulk_insert(prereq_table, prereq_rows)

    tm_table = sa.table(
        "tasks_master",
        sa.column("id"), sa.column("skill_id"), sa.column("question_text"),
        sa.column("question_latex"), sa.column("answer_type"), sa.column("correct_answer"),
        sa.column("answer_options"), sa.column("difficulty"),
        sa.column("irt_discrimination"), sa.column("irt_difficulty"), sa.column("irt_guessing"),
        sa.column("solution_steps"), sa.column("hints"), sa.column("distractor_meta"),
        sa.column("is_active"),
    )
    op.bulk_insert(tm_table, _build_tasks())


def downgrade() -> None:
    op.drop_table("tasks_master")
    op.drop_table("skill_prerequisites")
    op.drop_table("knowledge_hierarchy")
