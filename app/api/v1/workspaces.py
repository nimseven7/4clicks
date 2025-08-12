from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.params import ProjectParams, ProjectWorkspaceParams
from app.databases.database import get_db_session
from app.databases.models import VariableType
from app.exceptions.exceptions import TerraformNotInitializedError
from app.schemas import WorkspaceCreateInput, WorkspaceListResponse, WorkspaceOutput
from app.schemas.workspace_schema import DeploymentVarsResponse
from app.services import workspace_services
from app.services.variable_services import VariableService
from app.var_type import TFVars

router = APIRouter(prefix="/projects/{project}/workspaces", tags=["Workspaces"])


@router.get(
    "/",
    response_model=WorkspaceListResponse,
    responses={
        404: {},
        400: {},
        409: {"description": "Conflict: workspace not initialized"},
    },
)
async def get_workspaces(
    params: ProjectParams = Depends(),
):
    """
    Get all workspaces for a project.
    """
    try:
        await workspace_services.check_project_exists(params.project)
        await workspace_services.check_project_initialized(params.project)
    except (FileNotFoundError, NotADirectoryError) as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        ) from err
    except RuntimeError as err:
        raise HTTPException(
            status_code=500,
            detail=str(err),
        ) from err
    except TerraformNotInitializedError as err:
        raise HTTPException(
            status_code=409,
            detail=str(err),
        ) from err
    workspaces = await workspace_services.get_workspaces(params.project)
    return WorkspaceListResponse(workspaces=workspaces)


@router.post("/", response_model=WorkspaceOutput, status_code=201, responses={404: {}})
async def create_workspace(
    workspace: WorkspaceCreateInput,
    params: ProjectParams = Depends(),
):
    """
    Create a new workspace for a project.
    """
    try:
        await workspace_services.check_project_exists(params.project)
    except (FileNotFoundError, NotADirectoryError) as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        ) from err
    res = await workspace_services.create_workspace(params.project, workspace.name)
    return res


@router.post(
    "/{workspace}/activate",
    response_model=WorkspaceOutput,
    status_code=200,
    responses={404: {}},
)
async def activate_workspace(
    params: ProjectWorkspaceParams = Depends(),
):
    """
    Activate a workspace for a project.
    """
    try:
        await workspace_services.check_workspace_exists(
            params.project, params.workspace
        )
    except (FileNotFoundError, NotADirectoryError) as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        ) from err
    res = await workspace_services.activate_workspace(params.project, params.workspace)
    return res


@router.delete("/{workspace}", status_code=204, responses={404: {}})
async def delete_workspace(
    params: ProjectWorkspaceParams = Depends(),
):
    """
    Delete a workspace for a project.
    """
    try:
        await workspace_services.check_workspace_exists(
            params.project, params.workspace
        )
    except (FileNotFoundError, NotADirectoryError) as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        ) from err
    await workspace_services.delete_workspace(params.project, params.workspace)


@router.get(
    "/{workspace}/tfvars",
    response_model=TFVars,
    responses={404: {"description": "Workspace not found"}},
)
async def get_workspace_tfvars(
    params: ProjectWorkspaceParams = Depends(),
):
    """
    Get the Terraform variables for a workspace.
    Return the example variables if not created yet.
    Kept to get the content of the workspace tfvars file.
    """
    try:
        await workspace_services.check_workspace_exists(
            params.project, params.workspace
        )
    except (FileNotFoundError, NotADirectoryError) as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        ) from err
    tfvars = await workspace_services.get_workspace_tfvars(
        params.project, params.workspace
    )
    return tfvars


@router.post(
    "/{workspace}/tfvars",
    response_model=TFVars,
    status_code=201,
    responses={404: {"description": "Workspace not found"}},
)
async def create_workspace_tfvars(
    tfvars: TFVars,
    params: ProjectWorkspaceParams = Depends(),
):
    """
    Create a Terraform variable file for a workspace.
    The variable file would be created if it does not exist.
    The created variable file would be overwritten by the terraform plan and apply commands
    with database fetched variables.
    """
    try:
        await workspace_services.check_workspace_exists(
            params.project, params.workspace
        )
    # TODO: Use WorkspaceNotFoundError instead of FileNotFoundError
    except (FileNotFoundError, NotADirectoryError) as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        ) from err
    try:
        await workspace_services.create_workspace_tfvars(
            params.project, params.workspace, tfvars
        )
        tfvars = await workspace_services.get_workspace_tfvars(
            params.project, params.workspace
        )
    except RuntimeError as err:
        raise HTTPException(
            status_code=500,
            detail=str(err),
        ) from err
    return tfvars


@router.put(
    "/{workspace}/tfvars",
    response_model=TFVars,
    status_code=200,
    responses={404: {"description": "Workspace not found"}},
)
async def update_workspace_tfvars(
    tfvars: TFVars,
    params: ProjectWorkspaceParams = Depends(),
):
    """
    Update the Terraform variable file for a workspace.
    This will overwrite the existing file with the provided variables.
    The updated variable file would be overwritten by the terraform plan and apply commands
    with database fetched variables.
    """
    try:
        await workspace_services.check_workspace_exists(
            params.project, params.workspace
        )
    except (FileNotFoundError, NotADirectoryError) as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        ) from err
    try:
        await workspace_services.update_workspace_tfvars(
            params.project, params.workspace, tfvars
        )
        tfvars = await workspace_services.get_workspace_tfvars(
            params.project, params.workspace
        )
    except RuntimeError as err:
        raise HTTPException(
            status_code=500,
            detail=str(err),
        ) from err
    return tfvars


@router.get(
    "/{workspace}/deployment-vars",
    response_model=DeploymentVarsResponse,
    responses={404: {"description": "Workspace not found"}},
)
async def get_deployment_vars(
    params: ProjectWorkspaceParams = Depends(),
    with_shebang: bool = True,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get deployment variables in shell script format.
    Returns variables with variable_type in ['PROJECT','INSTANCE'] formatted as bash export statements.
    Variables are grouped by their description field which serves as comment sections.
    """
    try:
        await workspace_services.check_workspace_exists(
            params.project, params.workspace
        )
    except (FileNotFoundError, NotADirectoryError) as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        ) from err

    # Fetch variables from database
    variable_service = VariableService(db)

    # Get PROJECT variables (shared across all instances)
    project_variables = await variable_service.get_variables_by_project(
        project_name=params.project,
        workspace_name=None,  # PROJECT variables don't have workspace_name
        variable_type=VariableType.PROJECT,
        limit=1000,  # Get all variables
    )

    # Get INSTANCE variables (specific to this workspace)
    instance_variables = await variable_service.get_variables_by_project(
        project_name=params.project,
        workspace_name=params.workspace,
        variable_type=VariableType.INSTANCE,
        limit=1000,  # Get all variables
    )

    # Combine all variables
    all_variables = project_variables + instance_variables

    # Build the shell script content
    script_lines = ["#!/bin/bash" if with_shebang else ""]

    # Group variables by their description (comment field)
    grouped_vars = {}  # type: ignore
    for var in all_variables:
        comment = var.description or "Variables"
        if comment not in grouped_vars:
            grouped_vars[comment] = []
        grouped_vars[comment].append(var)

    # Add variables grouped by comments
    for comment, vars_in_group in grouped_vars.items():
        script_lines.append(f"# {comment}")
        for var in vars_in_group:
            # Handle different value types
            if isinstance(var.value, str):
                value = f'"{var.value}"'
            else:
                value = str(var.value)
            script_lines.append(f"export {var.key}={value}")
        script_lines.append("")  # Empty line between groups

    content = "\n".join(script_lines)

    return DeploymentVarsResponse(content=content)
