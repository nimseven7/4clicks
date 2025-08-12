import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from app.services.terraform_services import (
    _set_workspace,
    execute_terraform_command,
    stream_terraform,
    stream_terraform_init,
    stream_terraform_plan,
    stream_terraform_apply,
    stream_terraform_destroy,
)


class TestExecuteTerraformCommand:
    @pytest.mark.anyio
    @patch("app.services.terraform_services.asyncio.create_subprocess_shell")
    @patch("app.services.terraform_services.logger")
    async def test_execute_terraform_command_success(self, mock_logger, mock_subprocess):
        # Arrange
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"Terraform output", b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc
        
        project_path = Path("/test/project")
        command = "terraform --version"
        
        # Act
        result = await execute_terraform_command(project_path, command)
        
        # Assert
        mock_subprocess.assert_called_once_with(
            command,
            cwd=project_path.resolve(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        mock_proc.communicate.assert_called_once()
        mock_logger.info.assert_called_once_with(f"Executing command: {command} from {project_path.resolve()}")
        assert result == "Terraform output"

    @pytest.mark.anyio
    @patch("app.services.terraform_services.asyncio.create_subprocess_shell")
    @patch("app.services.terraform_services.logger")
    async def test_execute_terraform_command_empty_output(self, mock_logger, mock_subprocess):
        # Arrange
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc
        
        # Act
        result = await execute_terraform_command(Path("/test"), "terraform init")
        
        # Assert
        assert result == ""


class TestStreamTerraform:
    @pytest.mark.anyio
    @patch("app.services.terraform_services.asyncio.create_subprocess_shell")
    @patch("app.services.terraform_services.logger")
    async def test_stream_terraform_success(self, mock_logger, mock_subprocess):
        # Arrange
        mock_stdout = AsyncMock()
        mock_stdout.readline.side_effect = [
            b"Line 1\n",
            b"Line 2\n", 
            b"Line 3\n",
            b""  # End of stream
        ]
        
        mock_proc = AsyncMock()
        mock_proc.stdout = mock_stdout
        mock_proc.returncode = 0  # Set successful return code
        mock_subprocess.return_value = mock_proc
        
        project_path = Path("/test/project")
        command = "terraform plan"
        
        # Act
        lines = []
        async for line in stream_terraform(project_path, command):
            lines.append(line)
        
        # Assert
        mock_subprocess.assert_called_once_with(
            command,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        mock_logger.info.assert_called_once_with(f"Executing command: {command} from {project_path}")
        assert lines == ["Line 1\n", "Line 2\n", "Line 3\n"]

    @pytest.mark.anyio
    @patch("app.services.terraform_services.asyncio.create_subprocess_shell")
    async def test_stream_terraform_no_stdout(self, mock_subprocess):
        # Arrange
        mock_proc = AsyncMock()
        mock_proc.stdout = None
        mock_proc.returncode = 0  # Set successful return code
        mock_subprocess.return_value = mock_proc
        
        # Act
        lines = []
        async for line in stream_terraform(Path("/test"), "terraform version"):
            lines.append(line)
        
        # Assert
        assert lines == []

    @pytest.mark.anyio
    @patch("app.services.terraform_services.asyncio.create_subprocess_shell")
    @patch("app.services.terraform_services.logger")
    async def test_stream_terraform_error_detected_in_output(self, mock_logger, mock_subprocess):
        # Arrange
        mock_stdout = AsyncMock()
        mock_stdout.readline.side_effect = [
            b"Starting terraform...\n",
            b"Error: Resource not found\n", 
            b"Additional error details\n",
            b""  # End of stream
        ]
        
        mock_proc = AsyncMock()
        mock_proc.stdout = mock_stdout
        mock_proc.returncode = 0  # Return code is 0 but we have Error: in output
        mock_subprocess.return_value = mock_proc
        
        project_path = Path("/test/project")
        command = "terraform plan"
        
        # Act & Assert
        with pytest.raises(RuntimeError, match="Command failed with exit code 0"):
            lines = []
            async for line in stream_terraform(project_path, command):
                lines.append(line)
        
        # Assert error was logged
        mock_logger.error.assert_any_call("Error detected in terraform output: Error: Resource not found")


class TestSetWorkspace:
    @pytest.mark.anyio
    @patch("app.services.terraform_services.execute_terraform_command")
    @patch("app.services.terraform_services.logger")
    async def test_set_workspace_success(self, mock_logger, mock_execute):
        # Arrange
        mock_execute.return_value = "Switched to workspace 'development'"
        project_path = Path("/test/project")
        workspace = "development"
        
        # Act
        result = await _set_workspace(project_path, workspace)
        
        # Assert
        mock_execute.assert_called_once_with(
            project_path, 
            "terraform workspace select development"
        )
        mock_logger.info.assert_called_once_with(f"Setting workspace: {workspace} in {project_path}")
        assert result == "Switched to workspace 'development'"


class TestStreamTerraformInit:
    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    @patch("app.services.terraform_services.logger")
    async def test_stream_terraform_init_success(self, mock_logger, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Switched to workspace 'dev'"
        
        async def mock_stream_generator():
            yield "Initializing...\n"
            yield "Terraform initialized!\n"
        
        mock_stream.return_value = mock_stream_generator()
        
        project_path = Path("/test/project")
        workspace = "dev"
        
        # Act
        lines = []
        async for line in stream_terraform_init(project_path, workspace):
            lines.append(line)
        
        # Assert
        mock_set_workspace.assert_awaited_once_with(project_path, workspace)
        mock_stream.assert_called_once_with(project_path, "terraform init")
        mock_logger.info.assert_called_once_with("Switched to workspace 'dev'")
        assert lines == ["Initializing...\n", "Terraform initialized!\n"]


class TestStreamTerraformPlan:
    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    @patch("app.services.terraform_services.get_var_file")
    @patch("app.services.terraform_services.logger")
    async def test_stream_terraform_plan_basic(self, mock_logger, mock_get_var_file, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        mock_get_var_file.return_value = Path("/test/prod.tfvars")
        
        async def mock_stream_generator():
            yield "Plan output\n"
        
        mock_stream.return_value = mock_stream_generator()
        
        # Act
        lines = []
        async for line in stream_terraform_plan(Path("/test"), "prod"):
            lines.append(line)
        
        # Assert
        mock_stream.assert_called_once_with(Path("/test"), "terraform plan -var-file=/test/prod.tfvars")
        assert lines == ["Plan output\n"]

    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    async def test_stream_terraform_plan_with_var_file(self, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        
        async def mock_stream_generator():
            return
            yield  # unreachable but keeps it as async generator
        
        mock_stream.return_value = mock_stream_generator()
        
        var_file = Path("/test/vars.tfvars")
        
        # Act
        async for _ in stream_terraform_plan(Path("/test"), "prod", var_file=var_file):
            pass
        
        # Assert
        mock_stream.assert_called_once_with(Path("/test"), "terraform plan -var-file=/test/vars.tfvars")

    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    @patch("app.services.terraform_services.get_var_file")
    async def test_stream_terraform_plan_with_output(self, mock_get_var_file, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        mock_get_var_file.return_value = Path("/test/prod.tfvars")
        
        async def mock_stream_generator():
            return
            yield  # unreachable but keeps it as async generator
        
        mock_stream.return_value = mock_stream_generator()
        
        output_file = Path("/test/plan.out")
        
        # Act
        async for _ in stream_terraform_plan(Path("/test"), "prod", output=output_file):
            pass
        
        # Assert
        mock_stream.assert_called_once_with(Path("/test"), "terraform plan -var-file=/test/prod.tfvars -out=/test/plan.out")

    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    async def test_stream_terraform_plan_with_both_options(self, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        
        async def mock_stream_generator():
            return
            yield  # unreachable but keeps it as async generator
        
        mock_stream.return_value = mock_stream_generator()
        
        var_file = Path("/test/vars.tfvars")
        output_file = Path("/test/plan.out")
        
        # Act
        async for _ in stream_terraform_plan(Path("/test"), "prod", var_file=var_file, output=output_file):
            pass
        
        # Assert
        expected_command = "terraform plan -var-file=/test/vars.tfvars -out=/test/plan.out"
        mock_stream.assert_called_once_with(Path("/test"), expected_command)


class TestStreamTerraformApply:
    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    @patch("app.services.terraform_services.get_var_file")
    async def test_stream_terraform_apply_basic(self, mock_get_var_file, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        mock_get_var_file.return_value = Path("/test/tfvars.d/prod.tfvars.json")
        
        async def mock_stream_generator():
            return
            yield  # unreachable but keeps it as async generator
        
        mock_stream.return_value = mock_stream_generator()
        
        # Act
        async for _ in stream_terraform_apply(Path("/test"), "prod"):
            pass
        
        # Assert
        mock_stream.assert_called_once_with(Path("/test"), "terraform apply -auto-approve -var-file=/test/tfvars.d/prod.tfvars.json")

    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    @patch("app.services.terraform_services.get_var_file")
    async def test_stream_terraform_apply_with_var_file(self, mock_get_var_file, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        mock_get_var_file.return_value = Path("/test/tfvars.d/prod.tfvars.json")
        
        async def mock_stream_generator():
            return
            yield  # unreachable but keeps it as async generator
        
        mock_stream.return_value = mock_stream_generator()
        
        var_file = Path("/test/vars.tfvars")
        
        # Act
        async for _ in stream_terraform_apply(Path("/test"), "prod", var_file=var_file):
            pass
        
        # Assert
        expected_command = "terraform apply -auto-approve -var-file=/test/vars.tfvars"
        mock_stream.assert_called_once_with(Path("/test"), expected_command)

    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    @patch("app.services.terraform_services.get_var_file")
    async def test_stream_terraform_apply_with_input(self, mock_get_var_file, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        mock_get_var_file.return_value = Path("/test/tfvars.d/prod.tfvars.json")
        
        async def mock_stream_generator():
            return
            yield  # unreachable but keeps it as async generator
        
        mock_stream.return_value = mock_stream_generator()
        
        input_file = Path("/test/plan.out")
        
        # Act
        async for _ in stream_terraform_apply(Path("/test"), "prod", input=input_file):
            pass
        
        # Assert
        expected_command = "terraform apply -auto-approve -var-file=/test/tfvars.d/prod.tfvars.json /test/plan.out"
        mock_stream.assert_called_once_with(Path("/test"), expected_command)

    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    async def test_stream_terraform_apply_with_both_options(self, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        
        async def mock_stream_generator():
            return
            yield  # unreachable but keeps it as async generator
        
        mock_stream.return_value = mock_stream_generator()
        
        var_file = Path("/test/vars.tfvars")
        input_file = Path("/test/plan.out")
        
        # Act
        async for _ in stream_terraform_apply(Path("/test"), "prod", var_file=var_file, input=input_file):
            pass
        
        # Assert
        expected_command = "terraform apply -auto-approve -var-file=/test/vars.tfvars /test/plan.out"
        mock_stream.assert_called_once_with(Path("/test"), expected_command)


class TestStreamTerraformDestroy:
    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    @patch("app.services.terraform_services.get_var_file")
    async def test_stream_terraform_destroy_basic(self, mock_get_var_file, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        mock_get_var_file.return_value = Path("/test/tfvars.d/prod.tfvars.json")
        
        async def mock_stream_generator():
            return
            yield  # unreachable but keeps it as async generator
        
        mock_stream.return_value = mock_stream_generator()
        
        # Act
        async for _ in stream_terraform_destroy(Path("/test"), "prod"):
            pass
        
        # Assert
        mock_stream.assert_called_once_with(Path("/test"), "terraform destroy -auto-approve -var-file=/test/tfvars.d/prod.tfvars.json")

    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    @patch("app.services.terraform_services.get_var_file")
    async def test_stream_terraform_destroy_with_var_file(self, mock_get_var_file, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Workspace set"
        mock_get_var_file.return_value = Path("/test/tfvars.d/prod.tfvars.json")
        
        async def mock_stream_generator():
            return
            yield  # unreachable but keeps it as async generator
        
        mock_stream.return_value = mock_stream_generator()
        
        var_file = Path("/test/vars.tfvars")
        
        # Act
        async for _ in stream_terraform_destroy(Path("/test"), "prod", var_file=var_file):
            pass
        
        # Assert
        expected_command = "terraform destroy -auto-approve -var-file=/test/vars.tfvars"
        mock_stream.assert_called_once_with(Path("/test"), expected_command)

    @pytest.mark.anyio
    @patch("app.services.terraform_services.stream_terraform")
    @patch("app.services.terraform_services._set_workspace")
    @patch("app.services.terraform_services.logger")
    @patch("app.services.terraform_services.get_var_file")
    async def test_stream_terraform_destroy_workspace_switching(self, mock_get_var_file, mock_logger, mock_set_workspace, mock_stream):
        # Arrange
        mock_set_workspace.return_value = "Switched to workspace 'production'"
        mock_get_var_file.return_value = Path("/test/project/tfvars.d/production.tfvars.json")
        
        async def mock_stream_generator():
            yield "Destroying resources...\n"
            yield "Destroy complete!\n"
        
        mock_stream.return_value = mock_stream_generator()
        
        project_path = Path("/test/project")
        workspace = "production"
        
        # Act
        lines = []
        async for line in stream_terraform_destroy(project_path, workspace):
            lines.append(line)
        
        # Assert
        mock_set_workspace.assert_called_once_with(project_path, workspace)
        mock_logger.info.assert_called_once_with("Switched to workspace 'production'")
        mock_stream.assert_called_once_with(project_path, "terraform destroy -auto-approve -var-file=/test/project/tfvars.d/production.tfvars.json")
        assert lines == ["Destroying resources...\n", "Destroy complete!\n"]
