"""Service layer for task template management."""

import os
from pathlib import Path
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.models import TaskTemplateType
from app.exceptions.exceptions import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    ServiceError,
    ValidationError,
)
from app.repositories.task_repository import TaskTemplateRepository
from app.schemas.task_schema import (
    TaskTemplateCreate,
    TaskTemplateListResponse,
    TaskTemplateResponse,
    TaskTemplateUpdate,
)

# Base tasks directory path
TASKS_DIR = Path(__file__).parent.parent.parent / "tasks"


class TaskTemplateService:
    """Service for task template operations."""

    def __init__(self, session: AsyncSession):
        self.repository = TaskTemplateRepository(session)
        self.session = session

    async def validate_file_exists(
        self, file_path: str, template_type: TaskTemplateType
    ) -> None:
        """Validate that the template file exists in the correct directory structure."""
        full_path = TASKS_DIR / file_path

        # Check if file exists
        if not full_path.exists() or not full_path.is_file():
            raise ValidationError(
                f"Template file not found: {file_path}. Please ensure the file exists in the tasks directory."
            )

        # Validate file path structure based on template type
        if template_type == TaskTemplateType.ANSIBLE:
            if not file_path.startswith("ansible/"):
                raise ValidationError(
                    "Ansible templates must be in the 'ansible/' directory. Example: 'ansible/deploy.yml'"
                )
            if not file_path.endswith((".yml", ".yaml")):
                raise ValidationError(
                    "Ansible templates must have .yml or .yaml extension."
                )
        elif template_type == TaskTemplateType.BASH:
            if not file_path.startswith("scripts/"):
                raise ValidationError(
                    "Bash templates must be in the 'scripts/' directory. Example: 'scripts/deploy.sh'"
                )
            if not file_path.endswith(".sh"):
                raise ValidationError("Bash templates must have .sh extension.")

    async def create_template(
        self, template_data: TaskTemplateCreate
    ) -> TaskTemplateResponse:
        """Create a new task template."""
        try:
            # Validate file exists and is in correct location
            await self.validate_file_exists(
                template_data.file_path, template_data.template_type
            )

            # Check if template with same name exists in project
            existing = await self.repository.get_by_name_and_project(
                template_data.name, template_data.project_name
            )
            if existing:
                raise EntityAlreadyExistsError(
                    f"Template '{template_data.name}' already exists in project '{template_data.project_name}'"
                )

            # Create the template
            template = await self.repository.create_from_schema(template_data)
            await self.session.flush()
            await self.session.refresh(template)
            await self.session.commit()

            return TaskTemplateResponse.model_validate(template)

        except Exception as e:
            await self.session.rollback()
            if isinstance(e, (ValidationError, EntityAlreadyExistsError)):
                raise
            raise ServiceError(f"Failed to create template: {str(e)}")

    async def get_template(self, template_id: int) -> TaskTemplateResponse:
        """Get a task template by ID."""
        try:
            template = await self.repository.get_by_id(template_id)
            if not template:
                raise EntityNotFoundError("Task template not found")

            return TaskTemplateResponse.model_validate(template)

        except EntityNotFoundError:
            raise
        except Exception as e:
            raise ServiceError(f"Failed to retrieve template: {str(e)}")

    async def update_template(
        self, template_id: int, template_data: TaskTemplateUpdate
    ) -> TaskTemplateResponse:
        """Update a task template."""
        try:
            # Get existing template
            existing = await self.repository.get_by_id(template_id)
            if not existing:
                raise EntityNotFoundError("Task template not found")

            # If file_path or template_type is being updated, validate the file
            if template_data.file_path or template_data.template_type:
                file_path = template_data.file_path or existing.file_path
                template_type = template_data.template_type or existing.template_type
                await self.validate_file_exists(file_path, template_type)

            # Check for name conflicts if name is being updated
            if template_data.name and template_data.name != existing.name:
                conflict = await self.repository.get_by_name_and_project(
                    template_data.name, existing.project_name
                )
                if conflict:
                    raise EntityAlreadyExistsError(
                        f"Template '{template_data.name}' already exists in project '{existing.project_name}'"
                    )

            # Update the template
            updated_template = await self.repository.update_from_schema(
                template_id, template_data
            )
            if not updated_template:
                raise EntityNotFoundError("Task template not found")

            await self.session.commit()
            return TaskTemplateResponse.model_validate(updated_template)

        except Exception as e:
            await self.session.rollback()
            if isinstance(
                e, (ValidationError, EntityNotFoundError, EntityAlreadyExistsError)
            ):
                raise
            raise ServiceError(f"Failed to update template: {str(e)}")

    async def delete_template(self, template_id: int) -> None:
        """Delete a task template."""
        try:
            template = await self.repository.get_by_id(template_id)
            if not template:
                raise EntityNotFoundError("Task template not found")

            # Check if template has associated tasks
            # Note: This is handled by the database foreign key constraint
            # but we could add a soft delete or warning here if needed

            success = await self.repository.delete(template_id)
            if not success:
                raise EntityNotFoundError("Task template not found")

            await self.session.commit()

        except Exception as e:
            await self.session.rollback()
            if isinstance(e, EntityNotFoundError):
                raise
            raise ServiceError(f"Failed to delete template: {str(e)}")

    async def list_templates_by_project(
        self,
        project_name: str,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
    ) -> TaskTemplateListResponse:
        """List task templates for a specific project."""
        try:
            templates = await self.repository.list_by_project(
                project_name, skip=skip, limit=limit, active_only=active_only
            )
            total = await self.repository.count_by_project(
                project_name, active_only=active_only
            )

            template_responses = [
                TaskTemplateResponse.model_validate(t) for t in templates
            ]

            return TaskTemplateListResponse(templates=template_responses, total=total)

        except Exception as e:
            raise ServiceError(f"Failed to list templates by project: {str(e)}")

    async def list_all_templates(
        self, skip: int = 0, limit: int = 100, active_only: bool = True
    ) -> TaskTemplateListResponse:
        """List all task templates."""
        try:
            templates = await self.repository.get_all_templates(
                skip=skip, limit=limit, active_only=active_only
            )

            template_responses = [
                TaskTemplateResponse.model_validate(t) for t in templates
            ]

            return TaskTemplateListResponse(
                templates=template_responses, total=len(template_responses)
            )

        except Exception as e:
            raise ServiceError(f"Failed to list all templates: {str(e)}")
