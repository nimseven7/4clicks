from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1.params import ProjectParams, ProjectWorkspaceParams
from app.api.v1.workspaces import get_workspaces, create_workspace, delete_workspace, get_deployment_vars, router
from app.exceptions.exceptions import TerraformNotInitializedError
from app.schemas import WorkspaceListResponse, WorkspaceOutput, WorkspaceCreateInput
from app.schemas.workspace_schema import DeploymentVarsResponse
from app.databases.models import VariableType
from app.schemas.variable_schema import VariableResponse


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestGetWorkspaces:
    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    @patch("app.services.workspace_services.check_project_initialized", new_callable=AsyncMock)
    @patch("app.services.workspace_services.get_workspaces", new_callable=AsyncMock)
    async def test_get_workspaces_success(self, mock_get_workspaces, mock_check_initialized, mock_check_exists):
        # Arrange
        params = ProjectParams(project="test-project")
        expected_workspaces = [
            WorkspaceOutput(name="workspace1", active=True),
            WorkspaceOutput(name="workspace2", active=False)
        ]
        mock_get_workspaces.return_value = expected_workspaces
        
        # Act
        result = await get_workspaces(params)
        
        # Assert
        mock_check_exists.assert_awaited_once_with("test-project")
        mock_check_initialized.assert_awaited_once_with("test-project")
        mock_get_workspaces.assert_awaited_once_with("test-project")
        assert isinstance(result, WorkspaceListResponse)
        assert result.workspaces == expected_workspaces

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    async def test_get_workspaces_project_not_found(self, mock_check_exists):
        # Arrange
        params = ProjectParams(project="non-existent")
        mock_check_exists.side_effect = FileNotFoundError("Project does not exist")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_workspaces(params)
        
        assert exc_info.value.status_code == 404
        assert "Project does not exist" in str(exc_info.value.detail)

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    async def test_get_workspaces_project_not_directory(self, mock_check_exists):
        # Arrange
        params = ProjectParams(project="not-a-dir")
        mock_check_exists.side_effect = NotADirectoryError("Project is not a directory")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_workspaces(params)
        
        assert exc_info.value.status_code == 404
        assert "Project is not a directory" in str(exc_info.value.detail)

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    @patch("app.services.workspace_services.check_project_initialized", new_callable=AsyncMock)
    async def test_get_workspaces_not_initialized(self, mock_check_initialized, mock_check_exists):
        # Arrange
        params = ProjectParams(project="uninitialized-project")
        mock_check_initialized.side_effect = TerraformNotInitializedError("Project not initialized")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_workspaces(params)
        
        assert exc_info.value.status_code == 409
        assert "Project not initialized" in str(exc_info.value.detail)

    def test_get_workspaces_endpoint_success(self, client):
        # Arrange & Act
        with patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock), \
             patch("app.services.workspace_services.check_project_initialized", new_callable=AsyncMock), \
             patch("app.services.workspace_services.get_workspaces", new_callable=AsyncMock) as mock_get_workspaces:
            mock_get_workspaces.return_value = [
                WorkspaceOutput(name="test-workspace", active=True)
            ]
            response = client.get("/projects/test-project/workspaces/")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        assert len(data["workspaces"]) == 1
        assert data["workspaces"][0]["name"] == "test-workspace"
        assert data["workspaces"][0]["active"] is True


class TestCreateWorkspace:
    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    @patch("app.services.workspace_services.create_workspace", new_callable=AsyncMock)
    async def test_create_workspace_success(self, mock_create_workspace, mock_check_exists):
        # Arrange
        workspace_input = WorkspaceCreateInput(name="new-workspace")
        params = ProjectParams(project="test-project")
        expected_output = WorkspaceOutput(name="new-workspace", active=True)
        mock_create_workspace.return_value = expected_output
        
        # Act
        result = await create_workspace(workspace_input, params)
        
        # Assert
        mock_check_exists.assert_awaited_once_with("test-project")
        mock_create_workspace.assert_awaited_once_with("test-project", "new-workspace")
        assert result == expected_output

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    async def test_create_workspace_project_not_found(self, mock_check_exists):
        # Arrange
        workspace_input = WorkspaceCreateInput(name="test-workspace")
        params = ProjectParams(project="non-existent")
        mock_check_exists.side_effect = FileNotFoundError("Project does not exist")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await create_workspace(workspace_input, params)
        
        assert exc_info.value.status_code == 404
        assert "Project does not exist" in str(exc_info.value.detail)

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock)
    async def test_create_workspace_project_not_directory(self, mock_check_exists):
        # Arrange
        workspace_input = WorkspaceCreateInput(name="test-workspace")
        params = ProjectParams(project="not-a-dir")
        mock_check_exists.side_effect = NotADirectoryError("Project is not a directory")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await create_workspace(workspace_input, params)
        
        assert exc_info.value.status_code == 404
        assert "Project is not a directory" in str(exc_info.value.detail)

    def test_create_workspace_endpoint_success(self, client):
        # Arrange & Act
        with patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock), \
             patch("app.services.workspace_services.create_workspace", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = WorkspaceOutput(name="new-workspace", active=True)
            response = client.post("/projects/test-project/workspaces/", json={"name": "new-workspace"})
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new-workspace"
        assert data["active"] is True

    def test_create_workspace_endpoint_project_not_found(self, client):
        # Arrange & Act
        with patch("app.services.workspace_services.check_project_exists", new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = FileNotFoundError("Project does not exist")
            response = client.post("/projects/non-existent/workspaces/", json={"name": "test-workspace"})
        
        # Assert
        assert response.status_code == 404
        assert "Project does not exist" in response.json()["detail"]


class TestDeleteWorkspace:
    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_workspace_exists", new_callable=AsyncMock)
    @patch("app.services.workspace_services.delete_workspace", new_callable=AsyncMock)
    async def test_delete_workspace_success(self, mock_delete_workspace, mock_check_workspace):
        # Arrange
        params = ProjectWorkspaceParams(project="test-project", workspace="test-workspace")
        
        # Act
        await delete_workspace(params)
        
        # Assert
        mock_check_workspace.assert_awaited_once_with("test-project", "test-workspace")
        mock_delete_workspace.assert_awaited_once_with("test-project", "test-workspace")

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_workspace_exists", new_callable=AsyncMock)
    async def test_delete_workspace_not_found(self, mock_check_workspace):
        # Arrange
        params = ProjectWorkspaceParams(project="test-project", workspace="non-existent")
        mock_check_workspace.side_effect = FileNotFoundError("Workspace does not exist")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await delete_workspace(params)
        
        assert exc_info.value.status_code == 404
        assert "Workspace does not exist" in str(exc_info.value.detail)

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_workspace_exists", new_callable=AsyncMock)
    async def test_delete_workspace_project_not_directory(self, mock_check_workspace):
        # Arrange
        params = ProjectWorkspaceParams(project="not-a-dir", workspace="test-workspace")
        mock_check_workspace.side_effect = NotADirectoryError("Project is not a directory")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await delete_workspace(params)
        
        assert exc_info.value.status_code == 404
        assert "Project is not a directory" in str(exc_info.value.detail)

    def test_delete_workspace_endpoint_success(self, client):
        # Arrange & Act
        with patch("app.services.workspace_services.check_workspace_exists", new_callable=AsyncMock), \
             patch("app.services.workspace_services.delete_workspace", new_callable=AsyncMock):
            response = client.delete("/projects/test-project/workspaces/test-workspace")
        
        # Assert
        assert response.status_code == 204

    def test_delete_workspace_endpoint_not_found(self, client):
        # Arrange & Act
        with patch("app.services.workspace_services.check_workspace_exists", new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = FileNotFoundError("Workspace does not exist")
            response = client.delete("/projects/test-project/workspaces/non-existent")
        
        # Assert
        assert response.status_code == 404
        assert "Workspace does not exist" in response.json()["detail"]

    def test_delete_workspace_invalid_names(self, client):
        # Arrange & Act
        response = client.delete("/projects/invalid@name!/workspaces/invalid@workspace!")
        
        # Assert
        assert response.status_code == 422  # Validation error


class TestGetDeploymentVars:
    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_workspace_exists", new_callable=AsyncMock)
    @patch("app.services.variable_services.VariableService")
    async def test_get_deployment_vars_success(self, mock_variable_service_class, mock_check_workspace, mock_db_session):
        # Arrange
        params = ProjectWorkspaceParams(project="test-project", workspace="test-workspace")
        
        # Mock variables
        from datetime import datetime
        
        project_var = VariableResponse(
            id=1,
            key="GOOGLE_CLIENT_ID",
            value="test-client-id",
            description="SSO Google",
            variable_type=VariableType.PROJECT,
            is_sensitive=False,
            project_name="test-project",
            workspace_name=None,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        instance_var = VariableResponse(
            id=2,
            key="INSTANCE_SIZE",
            value="t3.medium",
            description="Instance Configuration",
            variable_type=VariableType.INSTANCE,
            is_sensitive=False,
            project_name="test-project",
            workspace_name="test-workspace",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Mock the service
        mock_service = AsyncMock()
        mock_variable_service_class.return_value = mock_service
        mock_service.get_variables_by_project.side_effect = [
            [project_var],  # PROJECT variables
            [instance_var]  # INSTANCE variables
        ]
        
        # Act
        result = await get_deployment_vars(params, mock_db_session)
        
        # Assert
        mock_check_workspace.assert_awaited_once_with("test-project", "test-workspace")
        assert isinstance(result, DeploymentVarsResponse)
        assert "#!/bin/bash" in result.content
        assert "# SSO Google" in result.content
        assert 'export GOOGLE_CLIENT_ID="test-client-id"' in result.content
        assert "# Instance Configuration" in result.content
        assert 'export INSTANCE_SIZE="t3.medium"' in result.content

    @pytest.mark.anyio
    @patch("app.services.workspace_services.check_workspace_exists", new_callable=AsyncMock)
    async def test_get_deployment_vars_workspace_not_found(self, mock_check_workspace, mock_db_session):
        # Arrange
        params = ProjectWorkspaceParams(project="test-project", workspace="non-existent")
        mock_check_workspace.side_effect = FileNotFoundError("Workspace does not exist")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_deployment_vars(params, mock_db_session)
        
        assert exc_info.value.status_code == 404
        assert "Workspace does not exist" in str(exc_info.value.detail)

    def test_get_deployment_vars_endpoint_success(self, client):
        # Arrange & Act
        with patch("app.services.workspace_services.check_workspace_exists", new_callable=AsyncMock), \
             patch("app.services.variable_services.VariableService") as mock_service_class:
            
            # Mock variables
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.get_variables_by_project.side_effect = [[], []]  # Empty variables
            
            response = client.get("/projects/test-project/workspaces/test-workspace/deployment-vars")
        
        # Assert
        assert response.status_code == 200
        result = response.json()
        assert "content" in result
        assert "#!/bin/bash" in result["content"]


@pytest.fixture
def mock_db_session():
    return AsyncMock()
