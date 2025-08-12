from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.databases.models import Inventory, IPAddress
from app.repositories import BaseRepository


class InventoryRepository(BaseRepository[Inventory]):
    """Repository for managing inventory operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Inventory, session)

    async def get_by_name_and_project(
        self,
        name: str,
        project_name: Optional[str] = None,
        workspace_name: Optional[str] = None,
    ) -> Optional[Inventory]:
        """Get inventory by name, project, and workspace."""
        conditions = [Inventory.name == name]
        if project_name is not None:
            conditions.append(Inventory.project_name == project_name)
        if workspace_name is not None:
            conditions.append(Inventory.workspace_name == workspace_name)

        query = (
            select(Inventory)
            .where(and_(*conditions))
            .options(selectinload(Inventory.ip_addresses))
        )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name_and_project_only(
        self, name: str, project_name: str
    ) -> Optional[Inventory]:
        """
        Get inventory by name and project only (ignoring workspace) to check unique constraint.
        """  # noqa: E501
        query = (
            select(Inventory)
            .where(
                and_(
                    Inventory.name == name,
                    Inventory.project_name == project_name,
                )
            )
            .options(selectinload(Inventory.ip_addresses))
        )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_project_workspace(
        self, project_name: str, workspace_name: Optional[str] = None
    ) -> List[Inventory]:
        """Get all inventory items for a project and workspace."""
        conditions = [Inventory.project_name == project_name]
        if workspace_name is not None:
            conditions.append(Inventory.workspace_name == workspace_name)

        query = (
            select(Inventory)
            .where(and_(*conditions))
            .options(selectinload(Inventory.ip_addresses))
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())


class IPAddressRepository(BaseRepository[IPAddress]):
    """Repository for managing IP address operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(IPAddress, session)

    async def get_by_ip(self, ip: str) -> Optional[IPAddress]:
        """Get IP address by IP string."""
        query = select(IPAddress).where(IPAddress.ip == ip)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_ip(
        self, ip: str, description: Optional[str] = None
    ) -> IPAddress:
        """Get existing IP or create new one."""
        existing = await self.get_by_ip(ip)
        if existing:
            return existing

        return await self.create(ip=ip, description=description)
