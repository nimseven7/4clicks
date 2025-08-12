"""Repository for managing task templates and tasks in the database."""

from typing import Any, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.databases.models import Inventory, SSHKeyPair, Task, TaskTemplate
from app.repositories import BaseRepository
from app.schemas.task_schema import (
    TaskCreate,
)


class TaskTemplateRepository(BaseRepository[TaskTemplate]):
    """Repository for task template database operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(TaskTemplate, session)

    # TaskTemplate supports the standard get_by_name_and_project, list_by_project,
    # and count_by_project methods from BaseRepository, so we don't need to override them

    async def get_all_templates(
        self, skip: int = 0, limit: int = 100, active_only: bool = True
    ) -> List[TaskTemplate]:
        """List all task templates."""
        if active_only:
            return await self.get_all(skip=skip, limit=limit, is_active=True)
        else:
            return await self.get_all(skip=skip, limit=limit)


class TaskRepository(BaseRepository[Task]):
    """Repository for task execution database operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Task, session)

    async def create_from_task_schema(
        self, task_data: TaskCreate, template_id: int
    ) -> Task:
        """Create a new task execution from schema with template ID."""
        task_dict = task_data.model_dump(
            exclude={"template_id", "target_ip_addresses", "target_inventories"}
        )
        task_dict["template_id"] = template_id

        return await self.create(**task_dict)

    async def get_by_id(self, task_id: int) -> Optional[Task]:
        """Get a task by ID with template and target relationships."""
        result = await self.session.execute(
            select(Task)
            .options(
                selectinload(Task.template),
                selectinload(Task.target_ip_addresses),
                selectinload(Task.target_inventories).selectinload(
                    Inventory.ip_addresses
                ),
                selectinload(Task.ssh_key),
            )
            .where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_by_project(
        self,
        project_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
        **additional_filters: Any,
    ) -> List[Task]:
        """List tasks by project and optionally workspace."""
        query = select(Task).options(selectinload(Task.template))
        if project_name:
            query = query.where(Task.project_name == project_name)

        # Apply additional filters
        for key, value in additional_filters.items():
            if hasattr(Task, key) and value is not None:
                query = query.where(getattr(Task, key) == value)

        query = query.offset(skip).limit(limit).order_by(Task.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        task_id: int,
        status: str,
        logs: Optional[str] = None,
        exit_code: Optional[int] = None,
    ) -> Optional[Task]:
        """Update task status and execution details."""
        update_data: dict = {"status": status}
        if logs is not None:
            update_data["logs"] = logs
        if exit_code is not None:
            update_data["exit_code"] = exit_code

        return await self.update(task_id, **update_data)

    async def list_all_tasks(self, skip: int = 0, limit: int = 100) -> List[Task]:
        """List all tasks with template relationships."""
        query = (
            select(Task)
            .options(selectinload(Task.template))
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())


class SSHKeyRepository(BaseRepository[SSHKeyPair]):
    """Repository for SSH key pair database operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(SSHKeyPair, session)

    # SSHKeyPair supports the standard get_by_name_and_project, list_by_project,
    # and count_by_project methods from BaseRepository, so we don't need to override them

    async def get_by_fingerprint(self, fingerprint: str) -> Optional[SSHKeyPair]:
        """Get an SSH key pair by fingerprint."""
        result = await self.session.execute(
            select(SSHKeyPair).where(SSHKeyPair.fingerprint == fingerprint)
        )
        return result.scalar_one_or_none()

    async def update_last_used(self, ssh_key_id: int) -> Optional[SSHKeyPair]:
        """Update the last used timestamp for an SSH key."""
        from sqlalchemy.sql import func

        await self.session.execute(
            update(SSHKeyPair)
            .where(SSHKeyPair.id == ssh_key_id)
            .values(last_used_at=func.now())
        )

        return await self.get_by_id(ssh_key_id)

    async def get_all_active(
        self, skip: int = 0, limit: int = 100, active_only: bool = True
    ) -> List[SSHKeyPair]:
        """List all SSH key pairs."""
        if active_only:
            return await self.get_all(skip=skip, limit=limit, is_active=True)
        else:
            return await self.get_all(skip=skip, limit=limit)
