"""Repository for managing variables in the database."""

from typing import Any, List, Optional

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.models import Variable, VariableType
from app.repositories import BaseRepository
from app.schemas.variable_schema import VariableCreate, VariableResponse, VariableUpdate


class VariableRepository(BaseRepository[Variable]):
    """Repository for variable database operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Variable, session)

    # BaseRepository provides create() and get_by_id() methods

    async def get_by_key_and_project(
        self, key: str, project_name: str, workspace_name: Optional[str] = None
    ) -> Optional[Variable]:
        """Get a variable by key, project, and workspace."""
        query = select(Variable).where(
            and_(
                Variable.key == key,
                Variable.project_name == project_name,
                Variable.workspace_name == workspace_name,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_by_project(
        self,
        project_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
        **additional_filters: Any,
    ) -> List[Variable]:
        """List variables for a project and optional workspace."""
        workspace_name = additional_filters.get("workspace_name")
        variable_type = additional_filters.get("variable_type", VariableType.TERRAFORM)

        conditions = []
        if project_name:
            conditions.append(Variable.project_name == project_name)
        if workspace_name:
            conditions.append(Variable.workspace_name == workspace_name)
        if variable_type:
            conditions.append(Variable.variable_type == variable_type)
        query = select(Variable).where(and_(*conditions)).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        project_filter: Optional[str] = None,
        workspace_filter: Optional[str] = None,
        variable_type_filter: Optional[VariableType] = None,
    ) -> List[Variable]:
        """List all variables with optional filters."""
        query = select(Variable)

        filters = []
        if project_filter:
            filters.append(Variable.project_name == project_filter)
        if workspace_filter:
            filters.append(Variable.workspace_name == workspace_filter)
        if variable_type_filter:
            filters.append(Variable.variable_type == variable_type_filter)

        if filters:
            query = query.where(and_(*filters))

        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    # BaseRepository provides update() and delete() methods

    async def bulk_create(self, variables_data: List[VariableCreate]) -> List[Variable]:
        """Create multiple variables in bulk."""
        variables = [Variable(**var_data.model_dump()) for var_data in variables_data]
        self.session.add_all(variables)
        # Don't flush here - let the service handle transaction management
        return variables

    async def delete_by_project(
        self, project_name: str, workspace_name: Optional[str] = None
    ) -> int:
        """Delete all variables for a project/workspace.
        Returns count of deleted variables."""
        query = delete(Variable).where(
            and_(
                Variable.project_name == project_name,
                Variable.workspace_name == workspace_name,
            )
        )

        result = await self.session.execute(query)
        return result.rowcount or 0

    async def search_variables(
        self,
        search_term: str,
        project_name: Optional[str] = None,
        workspace_name: Optional[str] = None,
        variable_type: Optional[VariableType] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Variable]:
        """Search variables by key or description."""
        query = select(Variable).where(
            Variable.key.ilike(f"%{search_term}%")
            | Variable.description.ilike(f"%{search_term}%")
        )

        filters = []
        if project_name:
            filters.append(Variable.project_name == project_name)
        if workspace_name:
            filters.append(Variable.workspace_name == workspace_name)
        if variable_type:
            filters.append(Variable.variable_type == variable_type)

        if filters:
            query = query.where(and_(*filters))

        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
