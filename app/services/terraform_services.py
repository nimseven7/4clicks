import asyncio
import json
import re
from pathlib import Path
from typing import AsyncGenerator

from app.logger import logger
from app.services.variable_services import VariableService


async def stream_terraform(
    project_path: Path, command: str
) -> AsyncGenerator[str, None]:
    """
    Stream the output of a terraform command.
    """
    logger.info(f"Executing command: {command} from {project_path}")
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=project_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    output_lines = []
    error_detected = False
    while True:
        if stdout := proc.stdout:
            line = await stdout.readline()
            if not line:
                break
            decoded_line = line.decode()
            output_lines.append(decoded_line)

            # Check for "Error:" string in the output
            if "Error:" in decoded_line:
                error_detected = True
                logger.error(
                    f"Error detected in terraform output: {decoded_line.strip()}"
                )

            yield decoded_line
        else:
            break

    # Wait for the process to complete and check return code
    await proc.wait()
    if proc.returncode != 0 or error_detected:
        logger.error(f"Command failed with exit code {proc.returncode}")
        error_output = "".join(output_lines)
        raise RuntimeError(
            f"Command failed with exit code {proc.returncode}: "
            f"{clean_terraform_errors(error_output)}"
        )


async def _set_workspace(project_path: Path, workspace: str) -> str:
    """
    Set the current workspace for the given project.
    """
    command = f"terraform workspace select {workspace}"
    logger.info(f"Setting workspace: {workspace} in {project_path}")
    return await execute_terraform_command(project_path, command)


def clean_terraform_errors(err: str) -> str:
    """
    Clean the error message by removing ANSII escape codes.
    """
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", err).strip()


async def execute_terraform_command(project_path: Path, command: str) -> str:
    """
    Execute a terraform command and return the output.
    """
    absolute_path = project_path.resolve()
    logger.info(f"Executing command: {command} from {absolute_path}")
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=absolute_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()

    if proc.returncode != 0:
        # log the error and raise an exception
        logger.error(
            f"Command failed with exit code {proc.returncode}: {stdout.decode()}"
        )
        # translate the error from the terminal output to a lisible error message
        raise RuntimeError(
            f"Command failed with exit code {proc.returncode}:"
            f"{clean_terraform_errors(stdout.decode())}"
        )

    return stdout.decode()


async def get_var_file(project_path: Path, workspace: str) -> Path:
    """
    Get the path to the var_file for the given workspace.
    Later will be implemented to check for the existence of the record from dynamodb,
    and if not found, create a new var_file with example variables.
    If the var_file does not exist, raise a FileNotFoundError.
    """
    var_file = Path(f"tfvars.d/{workspace}.tfvars.json")
    var_file_relative = project_path / var_file
    logger.info(f"Checking for var file: {var_file} in {project_path}")
    if not var_file_relative.exists():
        logger.error(f"Var file {var_file} does not exist for workspace {workspace}.")
        raise FileNotFoundError(f"Var file {var_file} does not exist.")
    return var_file


async def build_var_file(
    project_name: str, workspace: str, variable_service: VariableService
) -> Path:
    """
    Build the var_file for the given workspace from the database."""
    var_file = Path(f"tfvars.d/{workspace}.tfvars.json")
    var_file_relative = Path(f"infra/{project_name}/infra/terraform") / var_file
    variables = await variable_service.get_variables_by_project(project_name, workspace)
    if not variables:
        logger.error(f"No variables found for workspace {workspace} from the database.")
        raise FileNotFoundError(f"No variables found for workspace {workspace}.")

    # Transform the variables to a tfvars.json format
    _vars = {var.key: var.value for var in variables if not var.is_sensitive}

    var_file_relative.parent.mkdir(parents=True, exist_ok=True)

    with open(var_file_relative, "w") as f:
        json.dump(_vars, f)
    return var_file


async def stream_terraform_init(
    project_path: Path, workspace: str
) -> AsyncGenerator[str, None]:
    """
    Stream the output of the terraform init command.
    """
    res = await _set_workspace(project_path, workspace)
    logger.info(res)
    async for line in stream_terraform(project_path, "terraform init"):
        yield line


async def stream_terraform_plan(
    project_path: Path,
    workspace: str,
    vars: dict[str, str | int | float | bool] | None = None,
    var_file: Path | None = None,
    output: Path | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream the output of the terraform plan command.
    TODO: Add support for generating a plan file.
    TODO: Generate a var_file from the vars dict for the apply and destroy command.
    """
    res = await _set_workspace(project_path, workspace)
    logger.info(res)
    command = "terraform plan"
    if vars:
        for key, value in vars.items():
            command += f" -var='{key}={value}'"
    elif var_file:
        command += f" -var-file={var_file}"
    else:
        var_file_from_workspace = await get_var_file(project_path, workspace)
        command += f" -var-file={var_file_from_workspace}"
    if output:
        command += f" -out={output}"
    async for line in stream_terraform(project_path, command):
        yield line


async def stream_terraform_apply(
    project_path: Path,
    workspace: str,
    var_file: Path | None = None,
    vars: dict[str, str | int | float | bool] | None = None,
    input: Path | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream the output of the terraform apply command.
    TODO: Add support for applying a plan file.
    """
    res = await _set_workspace(project_path, workspace)
    logger.info(res)
    command = "terraform apply -auto-approve"
    if vars:
        for key, value in vars.items():
            command += f" -var='{key}={value}'"
    elif var_file:
        command += f" -var-file={var_file}"
    else:
        var_file_from_workspace = await get_var_file(project_path, workspace)
        command += f" -var-file={var_file_from_workspace}"
    if input:
        command += f" {input}"
    async for line in stream_terraform(project_path, command):
        yield line


async def stream_terraform_destroy(
    project_path: Path,
    workspace: str,
    var_file: Path | None = None,
    vars: dict[str, str | int | float | bool] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream the output of the terraform destroy command.
    TODO: Should only use the var_file generated by the plan command.
    """
    res = await _set_workspace(project_path, workspace)
    logger.info(res)
    command = "terraform destroy -auto-approve"
    if vars:
        for key, value in vars.items():
            command += f" -var='{key}={value}'"
    elif var_file:
        command += f" -var-file={var_file}"
    else:
        var_file_from_workspace = await get_var_file(project_path, workspace)
        command += f" -var-file={var_file_from_workspace}"
    async for line in stream_terraform(project_path, command):
        yield line
