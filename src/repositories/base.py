"""Repository Pattern — Generic Base"""
from __future__ import annotations

from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, pk) -> Optional[ModelT]:
        return self.session.get(self.model, pk)

    def get_by_id_or_raise(self, pk) -> ModelT:
        obj = self.session.get(self.model, pk)
        if obj is None:
            raise ValueError(f"{self.model.__tablename__} with pk={pk!r} not found")
        return obj

    def list_all(self, limit: int = 100, offset: int = 0) -> List[ModelT]:
        return list(
            self.session.scalars(select(self.model).offset(offset).limit(limit))
        )

    def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        self.session.flush()
        return obj

    def delete(self, obj: ModelT) -> None:
        self.session.delete(obj)
        self.session.flush()
