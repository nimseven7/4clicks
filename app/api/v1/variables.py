"""API endpoints for managing variables."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_handlers import handle_service_exceptions
from app.databases.database import get_db_session
from app.databases.models import VariableType
from app.logger import logger
from app.schemas.variable_schema import (
    VariableBulkImportRequest,
    VariableBulkImportResponse,
    VariableCreate,
    VariableExportResponse,
    VariableListResponse,
    VariableResponse,
    VariableShellImportRequest,
    VariableShellImportResponse,
    VariableStatisticsResponse,
    VariableUpdate,
    VariableValidationResponse,
)
from app.services.variable_services import VariableService

router = APIRouter(
    prefix="/variables",
    tags=["Variables"],
)


@router.get("/statistics", response_model=VariableStatisticsResponse)
@handle_service_exceptions
async def get_variable_statistics(db: AsyncSession = Depends(get_db_session)):
    """Get statistics about variables across all projects and workspaces."""
    service = VariableService(db)
    stats = await service.get_variable_statistics()
    return stats


@router.get("/search", response_model=List[VariableResponse])
@handle_service_exceptions
async def search_variables(
    q: str = Query(..., description="Search term"),
    project_name: Optional[str] = Query(None, description="Filter by project name"),
    workspace_name: Optional[str] = Query(None, description="Filter by workspace name"),
    variable_type: Optional[VariableType] = Query(
        None, description="Filter by variable type"
    ),
    skip: int = Query(0, ge=0, description="Number of variables to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of variables to return"),
    db: AsyncSession = Depends(get_db_session),
):
    """Search variables by key or description."""
    service = VariableService(db)
    variables = await service.search_variables(
        q, project_name, workspace_name, variable_type, skip, limit
    )
    return variables


@router.post("/", response_model=VariableResponse)
@handle_service_exceptions
async def create_variable(
    variable_data: VariableCreate, db: AsyncSession = Depends(get_db_session)
):
    """Create a new variable."""
    try:
        service = VariableService(db)
        variable = await service.create_variable(variable_data)
        await db.commit()  # Commit the transaction
        return variable
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create variable: {e}")
        raise e


@router.get("/{variable_id}", response_model=VariableResponse)
@handle_service_exceptions
async def get_variable(variable_id: int, db: AsyncSession = Depends(get_db_session)):
    """Get a variable by ID."""
    service = VariableService(db)
    variable = await service.get_variable(variable_id)
    return variable


@router.put("/{variable_id}", response_model=VariableResponse)
@handle_service_exceptions
async def update_variable(
    variable_id: int,
    variable_data: VariableUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    """Update a variable."""
    try:
        service = VariableService(db)
        variable = await service.update_variable(variable_id, variable_data)
        return variable
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update variable ID {variable_id}: {e}")
        raise


@router.delete("/{variable_id}", status_code=204)
@handle_service_exceptions
async def delete_variable(variable_id: int, db: AsyncSession = Depends(get_db_session)):
    """Delete a variable."""
    try:
        service = VariableService(db)
        success = await service.delete_variable(variable_id)
        if not success:
            return {"message": "Variable not found"}
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete variable ID {variable_id}: {e}")
        raise


@router.get("/", response_model=VariableListResponse)
@handle_service_exceptions
async def list_variables(
    skip: int = Query(0, ge=0, description="Number of variables to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of variables to return"),
    project_filter: Optional[str] = Query(None, description="Filter by project name"),
    workspace_filter: Optional[str] = Query(
        None, description="Filter by workspace name"
    ),
    variable_type_filter: Optional[VariableType] = Query(
        None, description="Filter by variable type"
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """List all variables with optional filtering."""
    service = VariableService(db)
    variables = await service.list_all_variables(
        skip, limit, project_filter, workspace_filter, variable_type_filter
    )
    # For simplicity, returning the count of retrieved variables.
    # In production, you might want to count total matching records separately.
    return VariableListResponse(variables=variables, total=len(variables))


@router.get("/project/{project_name}", response_model=List[VariableResponse])
@handle_service_exceptions
async def get_project_variables(
    project_name: str,
    workspace: str = Query(None, description="Workspace name"),
    variable_type: VariableType = Query(
        VariableType.TERRAFORM, description="Filter by variable type"
    ),
    skip: int = Query(0, ge=0, description="Number of variables to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of variables to return"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get variables for a specific project workspace."""
    service = VariableService(db)
    variables = await service.get_variables_by_project(
        project_name, workspace, variable_type, skip, limit
    )
    return variables


# === Use Case Endpoints ===


@router.post("/bulk-import", response_model=VariableBulkImportResponse)
@handle_service_exceptions
async def bulk_import_variables(
    import_data: VariableBulkImportRequest, db: AsyncSession = Depends(get_db_session)
):
    """Bulk import variables with conflict resolution."""
    try:
        service = VariableService(db)
        result = await service.bulk_import_variables(
            import_data.variables, import_data.overwrite_existing
        )
        await db.commit()  # Commit the transaction
        return result
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to bulk import variables: {e}")
        raise


@router.post("/clone")
@handle_service_exceptions
async def clone_workspace_variables(
    source_project: str = Query(..., description="Source project name"),
    source_workspace: str = Query(..., description="Source workspace name"),
    target_project: str = Query(..., description="Target project name"),
    target_workspace: str = Query(..., description="Target workspace name"),
    variable_type: VariableType = Query(
        VariableType.TERRAFORM, description="Variable type to clone"
    ),
    overwrite_existing: bool = Query(False, description="Overwrite existing variables"),
    db: AsyncSession = Depends(get_db_session),
):
    """Clone variables from one workspace to another."""
    try:
        service = VariableService(db)
        result = await service.clone_workspace_variables(
            source_project,
            source_workspace,
            target_project,
            target_workspace,
            variable_type,
            overwrite_existing,
        )
        await db.commit()  # Commit the transaction
        return result
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to clone workspace variables: {e}")
        raise


@router.delete("/cleanup")
@handle_service_exceptions
async def cleanup_workspace_variables(
    project_name: str = Query(..., description="Project name"),
    workspace_name: Optional[str] = Query(None, description="Workspace name"),
    db: AsyncSession = Depends(get_db_session),
):
    """Clean up all variables for a workspace."""
    try:
        service = VariableService(db)
        deleted_count = await service.cleanup_workspace_variables(
            project_name, workspace_name
        )
        await db.commit()  # Commit the transaction
        return {
            "message": f"Deleted {deleted_count} variables",
            "deleted_count": deleted_count,
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to clean up workspace variables: {e}")
        raise


@router.get("/export/terraform", response_model=VariableExportResponse)
@handle_service_exceptions
async def export_variables_terraform(
    project_name: str = Query(..., description="Project name"),
    workspace_name: Optional[str] = Query(None, description="Workspace name"),
    include_sensitive: bool = Query(False, description="Include sensitive variables"),
    db: AsyncSession = Depends(get_db_session),
):
    """Export variables in Terraform-compatible format."""
    service = VariableService(db)
    result = await service.export_variables_to_terraform_format(
        project_name, workspace_name, include_sensitive
    )
    return result


@router.get("/validate", response_model=VariableValidationResponse)
@handle_service_exceptions
async def validate_variables(
    project_name: str = Query(..., description="Project name"),
    workspace_name: Optional[str] = Query(None, description="Workspace name"),
    required_variables: Optional[str] = Query(
        None, description="Comma-separated list of required variable names"
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """Validate that all required variables are defined."""
    service = VariableService(db)

    # Parse required variables from comma-separated string
    required_vars = []
    if required_variables:
        required_vars = [
            var.strip() for var in required_variables.split(",") if var.strip()
        ]

    result = await service.validate_variable_references(
        project_name, workspace_name, required_vars
    )
    return result


@router.post("/import-shell", response_model=VariableShellImportResponse)
@handle_service_exceptions
async def import_variables_from_shell(
    import_data: VariableShellImportRequest, db: AsyncSession = Depends(get_db_session)
):
    """
    Import variables from shell script content.

    Parses export statements from shell scripts and creates variables in the database.
    Supports grouping variables by comments and handles different value types.

    - **shell_content**: Shell script content with export statements
    - **project_name**: Project name for the variables
    - **variable_type**: Type of variables (PROJECT or INSTANCE)
    - **workspace_name**: Workspace name (required for INSTANCE variables)
    - **comment_description**: Default description for variables without comments
    - **overwrite_existing**: Whether to overwrite existing variables
    """
    try:
        service = VariableService(db)
        result = await service.import_variables_from_shell_script(
            shell_content=import_data.shell_content,
            project_name=import_data.project_name,
            variable_type=import_data.variable_type,
            workspace_name=import_data.workspace_name,
            comment_description=import_data.comment_description,
            overwrite_existing=import_data.overwrite_existing,
        )
        await db.commit()  # Commit the transaction
        return result
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to import variables from shell script: {e}")
        raise
