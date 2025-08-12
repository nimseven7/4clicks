import json
from pathlib import Path

from app.exceptions.exceptions import TerraformNotInitializedError
from app.logger import logger
from app.schemas import WorkspaceOutput
from app.services.project_services import check_project_exists, get_project
from app.services.terraform_services import execute_terraform_command
from app.var_type import TFVars


async def activate_workspace(project_name: str, workspace: str) -> WorkspaceOutput:
    """
    Activate a terraform workspace for a given project.
    """
    res = await execute_terraform_command(
        Path(f"infra/{project_name}/infra/terraform"),
        f"terraform workspace select {workspace}",
    )
    logger.info(res)
    return WorkspaceOutput(name=workspace, active=True)


async def get_workspaces(project_name: str) -> list[WorkspaceOutput]:
    """
    Get all terraform workspaces for a given project.
    """
    res = await execute_terraform_command(
        Path(f"infra/{project_name}/infra/terraform"), "terraform workspace list"
    )
    wks = [wk for wk in res.splitlines() if wk != ""]
    # remove the '*' from the active workspace and set active to True
    # for the active workspace
    # and set active to False for the rest

    return [
        WorkspaceOutput(
            name=wk[2:] if wk.startswith("*") else wk.strip(), active=wk.startswith("*")
        )
        for wk in wks
    ]


async def create_workspace(project_name: str, workspace: str) -> WorkspaceOutput:
    """
    Create a new terraform workspace for a given project.
    """
    res = await execute_terraform_command(
        Path(f"infra/{project_name}/infra/terraform"),
        f"terraform workspace new {workspace}",
    )
    return WorkspaceOutput(name=workspace, active=True)


async def check_project_initialized(project_name: str) -> None:
    """
    Check if the project is initialized.
    """
    try:
        res = await execute_terraform_command(
            Path(f"infra/{project_name}/infra/terraform"),
            "terraform validate",
        )
    except RuntimeError as err:
        raise TerraformNotInitializedError(str(err)) from err


async def check_workspace_exists(project_name: str, workspace: str) -> None:
    """
    Check if the workspace exists for a given project.
    """
    await check_project_exists(project_name)
    workspaces = [wk.name for wk in await get_workspaces(project_name)]
    if workspace not in workspaces:
        raise FileNotFoundError(
            f"Workspace {workspace} does not exist in project {project_name}."
        )


async def delete_workspace(project_name: str, workspace: str) -> None:
    """
    Delete a terraform workspace for a given project.
    """
    # Switch to default workspace to ensure we're not deleting the active workspace
    res = await execute_terraform_command(
        Path(f"infra/{project_name}/infra/terraform"),
        "terraform workspace select default",
    )
    logger.info(res)

    # Then delete the target workspace
    res = await execute_terraform_command(
        Path(f"infra/{project_name}/infra/terraform"),
        f"terraform workspace delete {workspace}",
    )
    logger.info(res)
    logger.info(f"Workspace {workspace} deleted successfully.")


async def get_workspace_tfvars(project_name: str, workspace: str) -> TFVars:
    """
    Get the Terraform variables for a specific workspace in a project.
    """
    project_path = Path(f"infra/{project_name}")

    tfvars_path = project_path / "infra/terraform/tfvars.d"
    workspace_file = tfvars_path / f"{workspace}.tfvars.json"

    if not workspace_file.exists():
        return TFVars()

    with open(workspace_file, "r") as f:
        data = json.load(f)
        # Ensure the loaded data is a dictionary
        if not isinstance(data, dict):
            return TFVars()

        return TFVars.from_dict(data)


async def create_workspace_tfvars(
    project_name: str, workspace: str, tfvars: TFVars
) -> None:
    """
    Set the Terraform variables for a specific workspace in a project.
    """
    project_path = Path(f"infra/{project_name}")

    tfvars_path = project_path / "infra/terraform/tfvars.d"
    workspace_file = tfvars_path / f"{workspace}.tfvars.json"

    # Create the directory if it doesn't exist
    if not tfvars_path.exists():
        tfvars_path.mkdir(parents=True, exist_ok=True)

    # Write the tfvars to the file
    with open(workspace_file, "w") as f:
        json.dump(tfvars.model_dump(), f, indent=2)

    logger.info(
        f"Set Terraform variables for workspace '{workspace}' in project '{project_name}'."  # noqa: E501
    )


async def update_workspace_tfvars(
    project_name: str, workspace: str, tfvars: TFVars
) -> None:
    """
    Update the Terraform variables for a specific workspace in a project.
    """
    await create_workspace_tfvars(project_name, workspace, tfvars)
    logger.info(
        f"Updated Terraform variables for workspace '{workspace}' in project '{project_name}'."  # noqa: E501
    )
