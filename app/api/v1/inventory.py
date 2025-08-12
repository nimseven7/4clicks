from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_handlers import handle_service_exceptions
from app.databases.database import get_db_session
from app.schemas.inventory_schema import InventoryResponse, TerraformSyncResponse
from app.services.inventory_services import InventoryService

router = APIRouter(
    prefix="/projects/{project}/inventory",
    tags=["Inventory"],
)


@router.get("/", response_model=List[InventoryResponse])
@handle_service_exceptions
async def get_inventory(
    project: str,
    workspace: Optional[str] = Query(None, description="Filter by workspace"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get inventory items for a project and optional workspace."""
    service = InventoryService(db)
    return await service.get_inventory(project, workspace)


@router.post("/sync", response_model=TerraformSyncResponse)
@handle_service_exceptions
async def sync_inventory(
    project: str,
    workspace: Optional[str] = Query(None, description="Workspace name for sync"),
    db: AsyncSession = Depends(get_db_session),
):
    """Synchronize inventory from Terraform outputs."""
    service = InventoryService(db)
    return await service.sync_from_terraform_outputs(project, workspace)


@router.delete("/cleanup")
@handle_service_exceptions
async def cleanup_inventory(
    project: str,
    workspace: Optional[str] = Query(None, description="Workspace name for cleanup"),
    db: AsyncSession = Depends(get_db_session),
):
    """Clean up all inventory items for a project and optional workspace."""
    service = InventoryService(db)
    deleted_count = await service.cleanup_workspace_inventory(project, workspace)
    return {
        "message": f"Deleted {deleted_count} inventory items",
        "deleted_count": deleted_count,
        "project": project,
        "workspace": workspace,
    }
