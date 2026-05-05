"""
Diagnostic Service — Read-only repositories for shared knowledge tables.
NEVER writes to knowledge_hierarchy, skill_prerequisites, or tasks_master.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.models.knowledge import KnowledgeHierarchy, SkillPrerequisite, TaskMaster
from src.repositories.base import BaseRepository


class KnowledgeRepository(BaseRepository[KnowledgeHierarchy]):
    model = KnowledgeHierarchy

    def get_children(self, parent_id: str) -> List[KnowledgeHierarchy]:
        """All direct children of a node, sorted by sequence_order."""
        return list(
            self.session.scalars(
                select(KnowledgeHierarchy)
                .where(
                    KnowledgeHierarchy.parent_id == parent_id,
                    KnowledgeHierarchy.is_active == True,  # noqa: E712
                )
                .order_by(KnowledgeHierarchy.sequence_order)
            )
        )

    def get_by_level_and_grade(self, level: str, grade: int) -> List[KnowledgeHierarchy]:
        return list(
            self.session.scalars(
                select(KnowledgeHierarchy)
                .where(
                    KnowledgeHierarchy.level == level,
                    KnowledgeHierarchy.class_level_start <= grade,
                    KnowledgeHierarchy.class_level_end >= grade,
                    KnowledgeHierarchy.is_active == True,  # noqa: E712
                )
                .order_by(KnowledgeHierarchy.sequence_order)
            )
        )

    def get_subtopics_for_topic(self, topic_id: str) -> List[KnowledgeHierarchy]:
        """All L3 subtopics for an L2 topic."""
        return self.get_children(topic_id)

    def get_skills_for_subtopic(self, subtopic_id: str) -> List[KnowledgeHierarchy]:
        """All L4 atomic skills for an L3 subtopic."""
        return self.get_children(subtopic_id)


class SkillPrerequisiteRepository(BaseRepository[SkillPrerequisite]):
    model = SkillPrerequisite

    def get_prerequisites(
        self, skill_id: str, *, hard_only: bool = False
    ) -> List[SkillPrerequisite]:
        """Prerequisites for skill_id, ordered by weight desc."""
        conditions = [SkillPrerequisite.skill_id == skill_id]
        if hard_only:
            conditions.append(SkillPrerequisite.is_hard == True)  # noqa: E712
        return list(
            self.session.scalars(
                select(SkillPrerequisite)
                .where(and_(*conditions))
                .order_by(SkillPrerequisite.weight.desc())
            )
        )


class TaskRepository(BaseRepository[TaskMaster]):
    model = TaskMaster

    def get_tasks_for_skill(
        self,
        skill_id: str,
        *,
        difficulty: Optional[str] = None,
        exclude_ids: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[TaskMaster]:
        conditions = [
            TaskMaster.skill_id == skill_id,
            TaskMaster.is_active == True,  # noqa: E712
        ]
        if difficulty:
            conditions.append(TaskMaster.difficulty == difficulty)
        if exclude_ids:
            conditions.append(TaskMaster.id.notin_(exclude_ids))

        return list(
            self.session.scalars(
                select(TaskMaster)
                .where(and_(*conditions))
                .order_by(TaskMaster.irt_difficulty)
                .limit(limit)
            )
        )

    def get_task_by_difficulty_target(
        self,
        skill_id: str,
        target_b: float,
        *,
        exclude_ids: Optional[List[str]] = None,
    ) -> Optional[TaskMaster]:
        """
        Pick the task whose IRT b-parameter is closest to target_b.
        Used by all phases for ability-matched task selection.
        """
        candidates = self.get_tasks_for_skill(
            skill_id, exclude_ids=exclude_ids, limit=20
        )
        if not candidates:
            return None
        return min(candidates, key=lambda t: abs(float(t.irt_difficulty or 0) - target_b))
