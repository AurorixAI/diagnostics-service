"""
Diagnostic Service — Read-only mirrors of shared knowledge tables.

This service READS but NEVER WRITES to:
  knowledge_hierarchy   — L1–L4 skill tree
  skill_prerequisites   — prerequisite graph edges
  tasks_master          — task bank with IRT parameters

Source of truth: algo-back (monolith). These ORM classes mirror the schema.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from src.models.base import Base


class KnowledgeHierarchy(Base):
    """L1–L4 curriculum skills hierarchy (read-only)."""

    __tablename__ = "knowledge_hierarchy"

    id = Column(String(30), primary_key=True)          # e.g. "G5_T06", "G5_S06_01"
    level = Column(String(2), nullable=False)           # L1 | L2 | L3 | L4
    parent_id = Column(String(30), ForeignKey("knowledge_hierarchy.id"))
    name = Column(String(200), nullable=False)
    name_ru = Column(String(200), nullable=False)
    description = Column(Text)
    class_level_start = Column(Integer)
    class_level_end = Column(Integer)
    importance = Column(Integer, default=5)             # 1–10
    sequence_order = Column(Integer, default=0)
    cognitive_type = Column(String(20))
    is_active = Column(Boolean, default=True)

    parent = relationship(
        "KnowledgeHierarchy",
        remote_side=[id],
        backref="children",
    )
    prerequisites_as_skill = relationship(
        "SkillPrerequisite",
        foreign_keys="SkillPrerequisite.skill_id",
        back_populates="skill",
    )


class SkillPrerequisite(Base):
    """Prerequisite graph edges (read-only)."""

    __tablename__ = "skill_prerequisites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(
        String(30), ForeignKey("knowledge_hierarchy.id"), nullable=False, index=True
    )
    prerequisite_id = Column(
        String(30), ForeignKey("knowledge_hierarchy.id"), nullable=False
    )
    weight = Column(Numeric(4, 2), default=1.0)  # 0.0–1.0 dependency strength
    is_hard = Column(Boolean, default=True)       # hard = mandatory, soft = recommended

    skill = relationship(
        "KnowledgeHierarchy",
        foreign_keys=[skill_id],
        back_populates="prerequisites_as_skill",
    )
    prerequisite = relationship(
        "KnowledgeHierarchy",
        foreign_keys=[prerequisite_id],
    )


class TaskMaster(Base):
    """Task bank with IRT parameters (read-only for this service)."""

    __tablename__ = "tasks_master"

    id = Column(String(30), primary_key=True)
    skill_id = Column(String(30), ForeignKey("knowledge_hierarchy.id"), nullable=True)
    question_text = Column(Text, nullable=False)
    question_latex = Column(Text)
    answer_type = Column(String(20), nullable=False)   # mcq | open | numeric | etc.
    correct_answer = Column(Text, nullable=False)
    answer_options = Column(JSONB)
    difficulty = Column(String(1), nullable=False, default="B")  # A | B | C
    irt_discrimination = Column(Numeric(6, 4), default=1.0)       # a param
    irt_difficulty = Column(Numeric(6, 4), default=0.0)            # b param
    irt_guessing = Column(Numeric(6, 4), default=0.0)              # c param
    solution_steps = Column(JSONB)
    hints = Column(JSONB)
    distractor_meta = Column(JSONB)  # [{value, misconception}, ...]
    is_active = Column(Boolean, default=True)
