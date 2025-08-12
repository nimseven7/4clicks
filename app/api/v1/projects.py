from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.params import ProjectParams
from app.exceptions.exceptions import TerraformInitError
from app.schemas import ProjectDetailResponse, ProjectListResponse
from app.services import project_services

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("/", response_model=ProjectListResponse)
async def get_projects():
    """
    List all projects.
    """
    projects = await project_services.get_projects()
    return ProjectListResponse(projects=projects)


@router.get("/{project}", response_model=ProjectDetailResponse, responses={404: {}})
async def get_project(params: ProjectParams = Depends()):
    """
    Get project details with the tfvars.
    """
    project = await project_services.get_project(params.project)
    tfvars = await project_services.get_tfvars(params.project)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetailResponse(project=project, tfvars=tfvars)


@router.get("/{project}/variablesForm", response_model=dict, responses={404: {}})
async def get_project_variables_form(params: ProjectParams = Depends()):
    """
    Get project variables form.
    """
    project = await project_services.get_project_variables_form(params.project)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/{project}/init", responses={200: {"model": str}, 404: {}, 400: {}})
async def init_project(
    reconfigure: bool = False,
    upgrade: bool = False,
    migrate_state: bool = False,
    params: ProjectParams = Depends(),
):
    """
    Initialize a new project with terraform init command.

    We will add options in the near future to customize the init command
    like adding -reconfigure or -upgrade option.
    """
    try:
        await project_services.check_project_exists(params.project)
        await project_services.init_project(
            params.project,
            reconfigure=reconfigure,
            upgrade=upgrade,
            migrate_state=migrate_state,
        )
    except (FileNotFoundError, NotADirectoryError) as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        ) from err
    except TerraformInitError as err:
        raise HTTPException(
            status_code=400,
            detail=(
                str(err)
                + " Use the reconfigure, upgrade, or migrate_state options to fix the issue."  # noqa: E501
                " If not sure, please contact the administrator to check the log message."  # noqa: E501
            ),
        ) from err
    return f"Project {params.project} initialized"
