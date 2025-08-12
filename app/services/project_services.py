import json
from pathlib import Path

import hcl2

from app.exceptions import TerraformInitError
from app.logger import logger
from app.schemas import ProjectOutput
from app.services.terraform_services import execute_terraform_command
from app.var_type import TFVars


def _path_exists(path: Path) -> None:
    """
    Check if the given path exists and is a directory.
    Raises FileNotFoundError or NotADirectoryError if the checks fail.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path {path} does not exist. Please check your setup.")
    if not path.is_dir():
        raise NotADirectoryError(
            f"Path {path} is not a directory. Please check your setup."
        )


async def get_projects() -> list[ProjectOutput]:
    """
    Get all available projects from the infra directory.
    """

    infra_path = Path("infra")
    _path_exists(infra_path)

    dir_list = [
        ProjectOutput(name=project.name, description=await _get_description(project))
        for project in infra_path.glob("*/")
        if project.is_dir()
    ]

    return dir_list


async def get_project(project_name: str) -> ProjectOutput:
    """
    Get a project by its name.
    """
    project_path = Path(f"infra/{project_name}")
    _path_exists(project_path)

    description = await _get_description(project_path)
    return ProjectOutput(name=project_name, description=description)


async def get_tfvars(project_name: str) -> TFVars:
    """
    Get the Terraform example variables for a project.
    """
    project_path = Path(f"infra/{project_name}")
    _path_exists(project_path)

    tfvars_path = project_path / "infra/terraform/tfvars.d"
    example_file = tfvars_path / f"{project_name}.tfvars.json.example"

    if not example_file.exists():
        return TFVars()

    with open(example_file, "r") as f:
        content = json.load(f)
    if not isinstance(content, dict):
        logger.error(
            f"Invalid tfvars file format for {project_name}. Expected a JSON object."
        )
        raise ValueError(
            f"Invalid tfvars file format for {project_name}. Expected a JSON object."
        )

    return TFVars(**content)


async def check_project_exists(project_name: str) -> None:
    """
    Check if the project exists in the infra directory.
    """
    project_path = Path(f"infra/{project_name}")
    _path_exists(project_path)


async def init_project(
    project_name: str,
    reconfigure: bool = False,
    upgrade: bool = False,
    migrate_state: bool = False,
) -> None:
    """
    Initialize a new project.
    """
    project_path = Path(f"infra/{project_name}")
    # Initialize the project (e.g., run terraform init)
    # This is a placeholder for the actual initialization logic
    tf_path = project_path / "infra/terraform"
    _path_exists(tf_path)

    command = "terraform init"
    if reconfigure:
        command += " -reconfigure"
    if upgrade:
        command += " -upgrade"
    if migrate_state:
        command += " -migrate-state -force-copy"

    try:
        res = await execute_terraform_command(tf_path, command)
    except RuntimeError as err:
        raise TerraformInitError(str(err)) from err


async def _get_description(project_path: Path) -> str:
    """
    Get the description of a project from its README file.
    """
    readme_path = project_path / "README.md"
    if readme_path.exists():
        with open(readme_path, "r") as f:
            readme_content = f.read()
        # find the '## Description' section in the README file
        description_start = readme_content.find("## Description")
        if description_start != -1:
            description_end = readme_content.find("##", description_start + 1)
            if description_end == -1:
                description_end = len(readme_content)
            result = readme_content[description_start:description_end].strip()
            return result.split("## Description\n")[-1].strip()

    return ""


async def get_project_variables_form(project_name: str):
    project_path = Path(f"infra/{project_name}")
    _path_exists(project_path)

    variables_path = project_path / "infra/terraform/variables.tf"
    if not variables_path.exists():
        raise FileNotFoundError(f"Variables file not found for project {project_name}")
    with open(variables_path, "r") as f:
        content = hcl2.load(f)
    result = {}

    for var in content.get("variable", []):
        for name, attrs in var.items():
            result[name] = {
                "description": attrs.get("description", ""),
                "type": attrs.get("type", "string"),
                "default": attrs.get("default", None),
                "sensitive": attrs.get("sensitive", False),
                "validation": attrs.get("validation", {}),
            }
    return result
