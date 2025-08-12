import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from app.services.workspace_services import (
    get_workspaces,
    create_workspace,
    check_project_initialized,
    check_workspace_exists,
    delete_workspace
)
from app.schemas import WorkspaceOutput
from app.exceptions.exceptions import TerraformNotInitializedError


class TestGetWorkspaces:
    @pytest.mark.anyio
    @patch("app.services.workspace_services.execute_terraform_command", new_callable=AsyncMock)
    async def test_get_workspaces_success(self, mock_execute_terraform):
        # Arrange
        terraform_output = """  default
* development
  production
  staging
"""
        mock_execute_terraform.return_value = terraform_output
        
        # Act
        result = await get_workspaces("test-project")
        
        # Assert
        mock_execute_terraform.assert_awaited_once_with(
            Path("infra/test-project/infra/terraform"), 
            "terraform workspace list"
        )
        
        assert len(result) == 4
        assert all(isinstance(workspace, WorkspaceOutput) for workspace in result)
        
        # Check default workspace
        default_ws = next(ws for ws in result if ws.name == "default")
        assert default_ws.active is False
        
        # Check active workspace
        dev_ws = next(ws for ws in result if ws.name == "development")
        assert dev_ws.active is True
        
        # Check other workspaces
        prod_ws = next(ws for ws in result if ws.name == "production")
        assert prod_ws.active is False
        
        staging_ws = next(ws for ws in result if ws.name == "staging")
        assert staging_ws.active is False

    @pytest.mark.anyio
    @patch("app.services.workspace_services.execute_terraform_command", new_callable=AsyncMock)
    async def test_get_workspaces_only_default(self, mock_execute_terraform):
        # Arrange
        terraform_output = "* default\n"
        mock_execute_terraform.return_value = terraform_output
        
        # Act
        result = await get_workspaces("test-project")
        
        # Assert
        assert len(result) == 1
        assert result[0].name == "default"
        assert result[0].active is True

    @pytest.mark.anyio
    @patch("app.services.workspace_services.execute_terraform_command", new_callable=AsyncMock)
    async def test_get_workspaces_empty_output(self, mock_execute_terraform):
        # Arrange
        terraform_output = ""
        mock_execute_terraform.return_value = terraform_output
        
        # Act
        result = await get_workspaces("test-project")
        
        # Assert
        assert result == []


class TestCreateWorkspace:
    @pytest.mark.anyio
    @patch("app.services.workspace_services.execute_terraform_command", new_callable=AsyncMock)
    async def test_create_workspace_success(self, mock_execute_terraform):
        # Arrange
        mock_execute_terraform.return_value = "Created and switched to workspace \"new-workspace\"!"
        
        # Act
        result = await create_workspace("test-project", "new-workspace")
        
        # Assert
        mock_execute_terraform.assert_awaited_once_with(
            Path("infra/test-project/infra/terraform"),
            "terraform workspace new new-workspace"
        )
        
        assert isinstance(result, WorkspaceOutput)
        assert result.name == "new-workspace"
        assert result.active is True


class TestCheckProjectInitialized:
    @pytest.mark.anyio
    @patch("app.services.workspace_services.execute_terraform_command", new_callable=AsyncMock)
    async def test_check_project_initialized_success(self, mock_execute_terraform):
        # Arrange
        mock_execute_terraform.return_value = "Success! The configuration is valid."
        
        # Act
        await check_project_initialized("test-project")
        
        # Assert
        mock_execute_terraform.assert_awaited_once_with(
            Path("infra/test-project/infra/terraform"),
            "terraform validate"
        )

    @pytest.mark.anyio
    @patch("app.services.workspace_services.execute_terraform_command", new_callable=AsyncMock)
    async def test_check_project_initialized_not_initialized(self, mock_execute_terraform):
        # Arrange
        mock_execute_terraform.side_effect = RuntimeError("Error: Module not initialized")
        
        # Act & Assert
        with pytest.raises(TerraformNotInitializedError) as exc_info:
            await check_project_initialized("uninitialized-project")
        
        assert "Error: Module not initialized" in str(exc_info.value)

    @pytest.mark.anyio
    @patch("app.services.workspace_services.execute_terraform_command", new_callable=AsyncMock)
    async def test_check_project_initialized_validation_error(self, mock_execute_terraform):
        # Arrange
        mock_execute_terraform.side_effect = RuntimeError("Terraform configuration invalid")
        
        # Act & Assert
        with pytest.raises(TerraformNotInitializedError) as exc_info:
            await check_project_initialized("invalid-project")
        
        assert "Terraform configuration invalid" in str(exc_info.value)

class TestCheckWorkspaceExists:
    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    @patch("app.services.workspace_services.get_workspaces", new_callable=AsyncMock)
    async def test_check_workspace_exists_success(self, mock_get_workspaces, mock_check_project_exists):
        # Arrange
        mock_workspaces = [
            WorkspaceOutput(name="default", active=False),
            WorkspaceOutput(name="development", active=True),
            WorkspaceOutput(name="production", active=False)
        ]
        mock_get_workspaces.return_value = mock_workspaces
        
        # Act
        await check_workspace_exists("test-project", "development")
        
        # Assert
        mock_check_project_exists.assert_awaited_once_with("test-project")
        mock_get_workspaces.assert_awaited_once_with("test-project")

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    @patch("app.services.workspace_services.get_workspaces", new_callable=AsyncMock)
    async def test_check_workspace_exists_workspace_not_found(self, mock_get_workspaces, mock_check_project_exists):
        # Arrange
        mock_workspaces = [
            WorkspaceOutput(name="default", active=False),
            WorkspaceOutput(name="production", active=True)
        ]
        mock_get_workspaces.return_value = mock_workspaces
        
        # Act & Assert
        with pytest.raises(FileNotFoundError) as exc_info:
            await check_workspace_exists("test-project", "non-existent")
        
        assert "Workspace non-existent does not exist in project test-project" in str(exc_info.value)

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    async def test_check_workspace_exists_project_not_found(self, mock_check_project_exists):
        # Arrange
        mock_check_project_exists.side_effect = FileNotFoundError("Project not found")
        
        # Act & Assert
        with pytest.raises(FileNotFoundError):
            await check_workspace_exists("non-existent-project", "development")


class TestDeleteWorkspace:
    @pytest.mark.anyio
    @patch("app.services.workspace_services.execute_terraform_command", new_callable=AsyncMock)
    @patch("app.services.workspace_services.logger")
    async def test_delete_workspace_success(self, mock_logger, mock_execute_terraform):
        # Arrange
        mock_execute_terraform.side_effect = [
            "Switched to workspace \"default\".",
            "Deleted workspace \"development\"!"
        ]
        
        # Act
        await delete_workspace("test-project", "development")
        
        # Assert
        assert mock_execute_terraform.call_count == 2
        
        # Check first call (switch to default)
        first_call = mock_execute_terraform.call_args_list[0]
        assert first_call[0][0] == Path("infra/test-project/infra/terraform")
        assert first_call[0][1] == "terraform workspace select default"
        
        # Check second call (delete workspace)
        second_call = mock_execute_terraform.call_args_list[1]
        assert second_call[0][0] == Path("infra/test-project/infra/terraform")
        assert second_call[0][1] == "terraform workspace delete development"
        
        # Check logging
        assert mock_logger.info.call_count == 3
        mock_logger.info.assert_any_call("Switched to workspace \"default\".")
        mock_logger.info.assert_any_call("Deleted workspace \"development\"!")
        mock_logger.info.assert_any_call("Workspace development deleted successfully.")

    @pytest.mark.anyio
    @patch("app.services.workspace_services.execute_terraform_command", new_callable=AsyncMock)
    @patch("app.services.workspace_services.logger")
    async def test_delete_workspace_switch_to_default_first(self, mock_logger, mock_execute_terraform):
        # Arrange
        mock_execute_terraform.side_effect = [
            "Switched to workspace \"default\".",
            "Deleted workspace \"staging\"!"
        ]
        
        # Act
        await delete_workspace("test-project", "staging")
        
        # Assert
        # Verify that we switch to default workspace first
        first_call = mock_execute_terraform.call_args_list[0]
        assert "terraform workspace select default" in first_call[0][1]
        
        # Then delete the target workspace
        second_call = mock_execute_terraform.call_args_list[1]
        assert "terraform workspace delete staging" in second_call[0][1]
