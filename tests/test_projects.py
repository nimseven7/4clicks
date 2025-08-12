from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1.params import ProjectParams
from app.api.v1.projects import get_projects, init_project, get_project, router
from app.exceptions.exceptions import TerraformInitError
from app.schemas import ProjectListResponse, ProjectOutput, ProjectDetailResponse


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestGetProjects:
    @pytest.mark.anyio
    @patch("app.services.project_services.get_projects", new_callable=AsyncMock)
    async def test_get_projects_success(self, mock_get_projects):
        # Arrange
        expected_projects = [
            ProjectOutput(name="project1", description="Description 1"),
            ProjectOutput(name="project2", description="Description 2")
        ]
        mock_get_projects.return_value = expected_projects
        
        # Act
        result = await get_projects()
        
        # Assert
        mock_get_projects.assert_awaited_once()
        assert isinstance(result, ProjectListResponse)
        assert result.projects == expected_projects
        assert len(result.projects) == 2

    @pytest.mark.anyio
    @patch("app.services.project_services.get_projects", new_callable=AsyncMock)
    async def test_get_projects_empty_list(self, mock_get_projects):
        # Arrange
        mock_get_projects.return_value = []
        
        # Act
        result = await get_projects()
        
        # Assert
        mock_get_projects.assert_awaited_once()
        assert isinstance(result, ProjectListResponse)
        assert result.projects == []

    def test_get_projects_endpoint(self, client):
        # Arrange & Act
        with patch("app.services.project_services.get_projects", new_callable=AsyncMock) as mock_get_projects:
            mock_get_projects.return_value = [
                ProjectOutput(name="test-project", description="Test description")
            ]
            response = client.get("/projects/")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "test-project"


class TestGetProject:
    @pytest.mark.anyio
    @patch("app.services.project_services.get_project", new_callable=AsyncMock)
    @patch("app.services.project_services.get_tfvars", new_callable=AsyncMock)
    async def test_get_project_success(self, mock_get_tfvars, mock_get_project):
        # Arrange
        params = ProjectParams(project="test-project")
        expected_project = ProjectOutput(name="test-project", description="Test description")
        expected_tfvars = {"environment": "dev", "region": "us-west-2"}
        mock_get_project.return_value = expected_project
        mock_get_tfvars.return_value = expected_tfvars
        
        # Act
        result = await get_project(params)
        
        # Assert
        mock_get_project.assert_awaited_once_with("test-project")
        mock_get_tfvars.assert_awaited_once_with("test-project")
        assert isinstance(result, ProjectDetailResponse)
        assert result.project == expected_project
        assert result.tfvars == expected_tfvars

    @pytest.mark.anyio
    @patch("app.services.project_services.get_project", new_callable=AsyncMock)
    @patch("app.services.project_services.get_tfvars", new_callable=AsyncMock)
    async def test_get_project_not_found(self, mock_get_tfvars, mock_get_project):
        # Arrange
        params = ProjectParams(project="non-existent")
        mock_get_project.return_value = None
        mock_get_tfvars.return_value = []
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_project(params)
        
        assert exc_info.value.status_code == 404
        assert "Project not found" in str(exc_info.value.detail)
        mock_get_project.assert_awaited_once_with("non-existent")

    @pytest.mark.anyio
    @patch("app.services.project_services.get_project", new_callable=AsyncMock)
    @patch("app.services.project_services.get_tfvars", new_callable=AsyncMock)
    async def test_get_project_empty_tfvars(self, mock_get_tfvars, mock_get_project):
        # Arrange
        params = ProjectParams(project="test-project")
        expected_project = ProjectOutput(name="test-project", description="Test description")
        mock_get_project.return_value = expected_project
        mock_get_tfvars.return_value = {}
        
        # Act
        result = await get_project(params)
        
        # Assert
        mock_get_project.assert_awaited_once_with("test-project")
        mock_get_tfvars.assert_awaited_once_with("test-project")
        assert isinstance(result, ProjectDetailResponse)
        assert result.project == expected_project
        assert result.tfvars == {}

    @pytest.mark.anyio
    @patch("app.services.project_services.get_project", new_callable=AsyncMock)
    @patch("app.services.project_services.get_tfvars", new_callable=AsyncMock)
    async def test_get_project_none_tfvars(self, mock_get_tfvars, mock_get_project):
        # Arrange
        params = ProjectParams(project="test-project")
        expected_project = ProjectOutput(name="test-project", description="Test description")
        mock_get_project.return_value = expected_project
        mock_get_tfvars.return_value = {}
        
        # Act
        result = await get_project(params)
        
        # Assert
        mock_get_project.assert_awaited_once_with("test-project")
        mock_get_tfvars.assert_awaited_once_with("test-project")
        assert isinstance(result, ProjectDetailResponse)
        assert result.project == expected_project
        assert result.tfvars == {}

    def test_get_project_endpoint_success(self, client):
        # Arrange & Act
        with patch("app.services.project_services.get_project", new_callable=AsyncMock) as mock_get_project, \
             patch("app.services.project_services.get_tfvars", new_callable=AsyncMock) as mock_get_tfvars:
            mock_get_project.return_value = ProjectOutput(name="test-project", description="Test description")
            mock_get_tfvars.return_value = {"environment": "dev"}
            response = client.get("/projects/test-project")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "project" in data
        assert "tfvars" in data
        assert data["project"]["name"] == "test-project"
        assert data["tfvars"] == {"environment": "dev"}

    def test_get_project_endpoint_not_found(self, client):
        # Arrange & Act
        with patch("app.services.project_services.get_project", new_callable=AsyncMock) as mock_get_project, \
             patch("app.services.project_services.get_tfvars", new_callable=AsyncMock) as mock_get_tfvars:
            mock_get_project.return_value = None
            mock_get_tfvars.return_value = {}
            response = client.get("/projects/non-existent")
        
        # Assert
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]

    def test_get_project_endpoint_empty_tfvars(self, client):
        # Arrange & Act
        with patch("app.services.project_services.get_project", new_callable=AsyncMock) as mock_get_project, \
             patch("app.services.project_services.get_tfvars", new_callable=AsyncMock) as mock_get_tfvars:
            mock_get_project.return_value = ProjectOutput(name="test-project", description="Test description")
            mock_get_tfvars.return_value = {}
            response = client.get("/projects/test-project")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["project"]["name"] == "test-project"
        assert data["tfvars"] == {}

class TestInitProject:
    @pytest.mark.anyio
    @patch("app.services.project_services.check_project_exists", new_callable=AsyncMock)
    @patch("app.services.project_services.init_project", new_callable=AsyncMock)
    async def test_init_project_success(self, mock_init_project, mock_check_exists):
        # Arrange
        params = ProjectParams(project="test-project")
        
        # Act
        result = await init_project(
            reconfigure=False,
            upgrade=False,
            migrate_state=False,
            params=params,
        )
        
        # Assert
        mock_check_exists.assert_awaited_once_with("test-project")
        mock_init_project.assert_awaited_once_with(
            "test-project",
            reconfigure=False,
            upgrade=False,
            migrate_state=False,
        )
        assert result == "Project test-project initialized"

    @pytest.mark.anyio
    @patch("app.services.project_services.check_project_exists", new_callable=AsyncMock)
    async def test_init_project_not_found(self, mock_check_exists):
        # Arrange
        params = ProjectParams(project="non-existent-project")
        mock_check_exists.side_effect = FileNotFoundError("Project does not exist")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await init_project(
                reconfigure=False,
                upgrade=False,
                migrate_state=False,
                params=params,
            )
        
        assert exc_info.value.status_code == 404
        assert "Project does not exist" in str(exc_info.value.detail)

    @pytest.mark.anyio
    @patch("app.services.project_services.check_project_exists", new_callable=AsyncMock)
    async def test_init_project_not_directory(self, mock_check_exists):
        # Arrange
        params = ProjectParams(project="not-a-directory")
        mock_check_exists.side_effect = NotADirectoryError("Project is not a directory")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await init_project(
                reconfigure=False,
                upgrade=False,
                migrate_state=False,
                params=params,
            )
        
        assert exc_info.value.status_code == 404
        assert "Project is not a directory" in str(exc_info.value.detail)

    @pytest.mark.anyio
    @patch("app.services.project_services.check_project_exists", new_callable=AsyncMock)
    @patch("app.services.project_services.init_project", new_callable=AsyncMock)
    async def test_init_project_terraform_init_error(self, mock_init_project, mock_check_exists):
        # Arrange
        params = ProjectParams(project="test-project")
        mock_init_project.side_effect = TerraformInitError("Terraform initialization failed")
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await init_project(
                reconfigure=False,
                upgrade=False,
                migrate_state=False,
                params=params,
            )
        
        assert exc_info.value.status_code == 400
        assert "Terraform initialization failed" in str(exc_info.value.detail)

    def test_init_project_endpoint_success(self, client):
        # Arrange & Act
        with patch("app.services.project_services.check_project_exists", new_callable=AsyncMock) as mock_check_exists, \
             patch("app.services.project_services.init_project", new_callable=AsyncMock) as mock_init_project:
            response = client.post("/projects/test-project/init")
        
        # Assert
        assert response.status_code == 200
        assert response.json() == "Project test-project initialized"

    def test_init_project_endpoint_not_found(self, client):
        # Arrange & Act
        with patch("app.services.project_services.check_project_exists", new_callable=AsyncMock) as mock_check_exists:
            mock_check_exists.side_effect = FileNotFoundError("Project does not exist")
            response = client.post("/projects/non-existent/init")
        
        # Assert
        assert response.status_code == 404
        assert "Project does not exist" in response.json()["detail"]

    def test_init_project_endpoint_terraform_error(self, client):
        # Arrange & Act
        with patch("app.services.project_services.check_project_exists", new_callable=AsyncMock) as mock_check_exists, \
             patch("app.services.project_services.init_project", new_callable=AsyncMock) as mock_init_project:
            mock_init_project.side_effect = TerraformInitError("Init failed")
            response = client.post("/projects/test-project/init")
        
        # Assert
        assert response.status_code == 400
        assert "Init failed" in response.json()["detail"]

    def test_init_project_invalid_project_name(self, client):
        # Arrange & Act
        response = client.post("/projects/invalid@name!/init")
        
        # Assert
        assert response.status_code == 422  # Validation error
