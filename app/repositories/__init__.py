"""Base repository pattern for database operations."""

from abc import ABC
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.database import Base

ModelType = TypeVar("ModelType", bound=Base)
SchemaType = TypeVar("SchemaType", bound=BaseModel)


class BaseRepository(Generic[ModelType], ABC):
    """Base repository class with common CRUD operations."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def create(self, **kwargs) -> ModelType:
        """Create a new record."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        # Don't flush here - let the service handle transaction management
        return instance

    async def create_from_schema(self, schema: BaseModel) -> ModelType:
        """Create a new record from a Pydantic schema."""
        return await self.create(**schema.model_dump())

    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """Get a record by ID."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)  # type: ignore
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        limit: Optional[int] = None,
        skip: Optional[int] = None,
        order_by: Optional[str] = None,
        **filters: Any,
    ) -> List[ModelType]:
        """Get all records with optional filtering, pagination."""
        query = select(self.model)

        # Apply filters
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                query = query.where(getattr(self.model, key) == value)

        # Apply ordering
        if order_by and hasattr(self.model, order_by):
            query = query.order_by(getattr(self.model, order_by).desc())
        elif hasattr(self.model, "created_at"):
            query = query.order_by(getattr(self.model, "created_at").desc())

        # Apply pagination
        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_filters(self, **filters: Any) -> Optional[ModelType]:
        """Get a single record by filters."""
        results = await self.get_all(limit=1, **filters)
        return results[0] if results else None

    async def get_by_name_and_project(
        self, name: str, project_name: Optional[str] = None
    ) -> Optional[ModelType]:
        """
        Get a record by name and project - common pattern across many models.
        Override in subclasses if the model doesn't have these fields.
        """
        if hasattr(self.model, "name") and hasattr(self.model, "project_name"):
            return await self.get_by_filters(name=name, project_name=project_name)
        raise NotImplementedError(
            f"{self.model.__name__} doesn't support get_by_name_and_project"
        )

    async def list_by_project(
        self,
        project_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
        **additional_filters: Any,
    ) -> List[ModelType]:
        """
        List records by project - common pattern across many models.
        Override in subclasses if the model doesn't have project_name field.
        """
        if not hasattr(self.model, "project_name"):
            raise NotImplementedError(
                f"{self.model.__name__} doesn't support list_by_project"
            )

        filters = {**additional_filters}
        if project_name:
            filters["project_name"] = project_name
        if active_only and hasattr(self.model, "is_active"):
            filters["is_active"] = True

        return await self.get_all(skip=skip, limit=limit, **filters)

    async def count_by_project(
        self,
        project_name: str | None = None,
        active_only: bool = True,
        **additional_filters: Any,
    ) -> int:
        """
        Count records by project - common pattern across many models.
        """
        if not hasattr(self.model, "project_name"):
            raise NotImplementedError(
                f"{self.model.__name__} doesn't support count_by_project"
            )

        filters = {**additional_filters}
        if project_name:
            filters["project_name"] = project_name
        if active_only and hasattr(self.model, "is_active"):
            filters["is_active"] = True

        return await self.count(**filters)

    async def update(self, id: int, **kwargs) -> Optional[ModelType]:
        """Update a record by ID."""
        await self.session.execute(
            update(self.model)
            .where(self.model.id == id)  # type: ignore
            .values(**kwargs)
        )
        return await self.get_by_id(id)

    async def update_from_schema(
        self, id: int, schema: BaseModel
    ) -> Optional[ModelType]:
        """Update a record from a Pydantic schema."""
        update_data = schema.model_dump(exclude_unset=True)
        if not update_data:
            return await self.get_by_id(id)
        return await self.update(id, **update_data)

    async def delete(self, id: int) -> bool:
        """Delete a record by ID."""
        result = await self.session.execute(
            delete(self.model).where(self.model.id == id)  # type: ignore
        )
        return result.rowcount > 0

    async def count(self, **filters: Any) -> int:
        """Count records with optional filtering."""
        query = select(func.count(self.model.id))  # type: ignore

        # Apply filters
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                query = query.where(getattr(self.model, key) == value)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def exists(self, **filters: Any) -> bool:
        """Check if a record exists with given filters."""
        query = select(self.model)

        # Apply filters
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                query = query.where(getattr(self.model, key) == value)

        query = query.limit(1)
        result = await self.session.execute(query)
        return result.first() is not None
