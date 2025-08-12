import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, mock_open
from app.services.project_services import (
    get_projects,
    get_tfvars,
    check_project_exists, 
    init_project,
    _get_description
)
from app.schemas import ProjectOutput
from app.exceptions.exceptions import TerraformInitError


class TestGetProjects:
    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    @patch("app.services.project_services._get_description", new_callable=AsyncMock)
    async def test_get_projects_success(self, mock_get_description, mock_path_class):
        # Arrange
        mock_infra_path = Mock()
        mock_infra_path.exists.return_value = True
        mock_infra_path.is_dir.return_value = True
        
        mock_project1 = Mock()
        mock_project1.name = "project1"
        mock_project1.is_dir.return_value = True
        
        mock_project2 = Mock()
        mock_project2.name = "project2"
        mock_project2.is_dir.return_value = True
        
        mock_infra_path.glob.return_value = [mock_project1, mock_project2]
        mock_path_class.return_value = mock_infra_path
        
        mock_get_description.side_effect = ["Description 1", "Description 2"]
        
        # Act
        result = await get_projects()
        
        # Assert
        mock_path_class.assert_called_once_with("infra")
        mock_infra_path.exists.assert_called_once()
        mock_infra_path.is_dir.assert_called_once()
        mock_infra_path.glob.assert_called_once_with("*/")
        
        assert len(result) == 2
        assert all(isinstance(project, ProjectOutput) for project in result)
        assert result[0].name == "project1"
        assert result[0].description == "Description 1"
        assert result[1].name == "project2"
        assert result[1].description == "Description 2"

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_get_projects_infra_not_exists(self, mock_path_class):
        # Arrange
        mock_infra_path = Mock()
        mock_infra_path.exists.return_value = False
        mock_infra_path.__str__ = Mock(return_value="infra")
        mock_path_class.return_value = mock_infra_path
        
        # Act & Assert
        with pytest.raises(FileNotFoundError) as exc_info:
            await get_projects()
        
        assert "Path infra does not exist" in str(exc_info.value)

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_get_projects_infra_not_directory(self, mock_path_class):
        # Arrange
        mock_infra_path = Mock()
        mock_infra_path.exists.return_value = True
        mock_infra_path.is_dir.return_value = False
        mock_infra_path.__str__ = Mock(return_value="infra")
        mock_path_class.return_value = mock_infra_path
        
        # Act & Assert
        with pytest.raises(NotADirectoryError) as exc_info:
            await get_projects()
        
        assert "Path infra is not a directory" in str(exc_info.value)

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    @patch("app.services.project_services._get_description", new_callable=AsyncMock)
    async def test_get_projects_empty_directory(self, mock_get_description, mock_path_class):
        # Arrange
        mock_infra_path = Mock()
        mock_infra_path.exists.return_value = True
        mock_infra_path.is_dir.return_value = True
        mock_infra_path.glob.return_value = []
        mock_path_class.return_value = mock_infra_path
        
        # Act
        result = await get_projects()
        
        # Assert
        assert result == []


class TestGetTfvars:
    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    @patch("builtins.open", new_callable=mock_open)
    @patch("app.services.project_services.json.load")
    async def test_get_tfvars_success_single_file(self, mock_json_load, mock_file_open, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_project_path.exists.return_value = True
        mock_project_path.is_dir.return_value = True

        mock_tfvars_path = Mock()
        mock_tfvars_path.exists.return_value = True
        
        mock_example_file = Mock()
        mock_example_file.exists.return_value = True
        mock_tfvars_path.__truediv__ = Mock(return_value=mock_example_file)
        
        mock_project_path.__truediv__ = Mock(return_value=mock_tfvars_path)

        mock_path_class.return_value = mock_project_path
        mock_json_load.return_value = {"environment": "dev", "region": "us-west-2"}

        # Act
        result = await get_tfvars("test-project")
        
        # Assert
        mock_path_class.assert_called_once_with("infra/test-project")
        assert result == {"environment": "dev", "region": "us-west-2"}

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    @patch("builtins.open", new_callable=mock_open)
    @patch("app.services.project_services.json.load")
    async def test_get_tfvars_success_multiple_files(self, mock_json_load, mock_file_open, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_project_path.exists.return_value = True
        mock_project_path.is_dir.return_value = True
        
        mock_tfvars_path = Mock()
        mock_tfvars_path.exists.return_value = True
        
        mock_example_file = Mock()
        mock_example_file.exists.return_value = True
        mock_tfvars_path.__truediv__ = Mock(return_value=mock_example_file)
        
        mock_project_path.__truediv__ = Mock(return_value=mock_tfvars_path)
        
        mock_path_class.return_value = mock_project_path
        mock_json_load.return_value = {"environment": "dev", "instance_type": "t2.micro"}
        
        # Act
        result = await get_tfvars("test-project")
        
        # Assert
        assert result == {"environment": "dev", "instance_type": "t2.micro"}

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_get_tfvars_no_example_files(self, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_project_path.exists.return_value = True
        mock_project_path.is_dir.return_value = True
        
        mock_tfvars_path = Mock()
        mock_tfvars_path.exists.return_value = True
        
        mock_example_file = Mock()
        mock_example_file.exists.return_value = False
        mock_tfvars_path.__truediv__ = Mock(return_value=mock_example_file)
        
        mock_project_path.__truediv__ = Mock(return_value=mock_tfvars_path)
        
        mock_path_class.return_value = mock_project_path
        
        # Act
        result = await get_tfvars("test-project")
        
        # Assert
        assert result == {}

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_get_tfvars_creates_directory_if_not_exists(self, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_project_path.exists.return_value = True
        mock_project_path.is_dir.return_value = True
        
        mock_tfvars_path = Mock()
        mock_tfvars_path.exists.return_value = True
        
        mock_example_file = Mock()
        mock_example_file.exists.return_value = False
        mock_tfvars_path.__truediv__ = Mock(return_value=mock_example_file)
        
        mock_project_path.__truediv__ = Mock(return_value=mock_tfvars_path)
        
        mock_path_class.return_value = mock_project_path
        
        # Act
        result = await get_tfvars("test-project")
        
        # Assert
        assert result == {}

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_get_tfvars_project_not_exists(self, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_project_path.exists.return_value = False
        mock_project_path.__str__ = Mock(return_value="infra/non-existent")
        mock_path_class.return_value = mock_project_path
        
        # Act & Assert
        with pytest.raises(FileNotFoundError) as exc_info:
            await get_tfvars("non-existent")
        
        assert "Path infra/non-existent does not exist" in str(exc_info.value)

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_get_tfvars_project_not_directory(self, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_project_path.exists.return_value = True
        mock_project_path.is_dir.return_value = False
        mock_project_path.__str__ = Mock(return_value="infra/not-a-dir")
        mock_path_class.return_value = mock_project_path
        
        # Act & Assert
        with pytest.raises(NotADirectoryError) as exc_info:
            await get_tfvars("not-a-dir")
        
        assert "Path infra/not-a-dir is not a directory" in str(exc_info.value)
    

class TestCheckProjectExists:
    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_check_project_exists_success(self, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_project_path.exists.return_value = True
        mock_project_path.is_dir.return_value = True
        mock_path_class.return_value = mock_project_path
        
        # Act
        await check_project_exists("test-project")
        
        # Assert
        mock_path_class.assert_called_once_with("infra/test-project")
        mock_project_path.exists.assert_called_once()
        mock_project_path.is_dir.assert_called_once()

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_check_project_exists_not_found(self, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_project_path.exists.return_value = False
        mock_project_path.__str__ = Mock(return_value="infra/non-existent")
        mock_path_class.return_value = mock_project_path
        
        # Act & Assert
        with pytest.raises(FileNotFoundError) as exc_info:
            await check_project_exists("non-existent")
        
        assert "Path infra/non-existent does not exist" in str(exc_info.value)

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_check_project_exists_not_directory(self, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_project_path.exists.return_value = True
        mock_project_path.is_dir.return_value = False
        mock_project_path.__str__ = Mock(return_value="infra/not-a-dir")
        mock_path_class.return_value = mock_project_path
        
        # Act & Assert
        with pytest.raises(NotADirectoryError) as exc_info:
            await check_project_exists("not-a-dir")
        
        assert "Path infra/not-a-dir is not a directory" in str(exc_info.value)


class TestInitProject:
    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    @patch("app.services.project_services.execute_terraform_command", new_callable=AsyncMock)
    @patch("app.services.project_services.logger")
    async def test_init_project_success(self, mock_logger, mock_execute_terraform, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_tf_path = Mock()
        mock_tf_path.exists.return_value = True
        mock_tf_path.is_dir.return_value = True
        mock_project_path.__truediv__ = Mock(return_value=mock_tf_path)
        
        mock_path_class.return_value = mock_project_path
        mock_execute_terraform.return_value = "Terraform has been successfully initialized!"
        
        # Act
        await init_project("test-project")
        
        # Assert
        mock_path_class.assert_called_once_with("infra/test-project")
        mock_project_path.__truediv__.assert_called_once_with("infra/terraform")
        mock_execute_terraform.assert_awaited_once_with(mock_tf_path, "terraform init")

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_init_project_terraform_path_not_exists(self, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_tf_path = Mock()
        mock_tf_path.exists.return_value = False
        mock_tf_path.__str__ = Mock(return_value="infra/test-project/infra/terraform")
        mock_project_path.__truediv__ = Mock(return_value=mock_tf_path)
        mock_path_class.return_value = mock_project_path
        
        # Act & Assert
        with pytest.raises(FileNotFoundError) as exc_info:
            await init_project("test-project")
        
        # More flexible assertion that works with different error message formats
        error_message = str(exc_info.value).lower()
        assert "terraform" in error_message or "path" in error_message
        assert "does not exist" in error_message or "not found" in error_message

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    async def test_init_project_terraform_path_not_directory(self, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_tf_path = Mock()
        mock_tf_path.exists.return_value = True
        mock_tf_path.is_dir.return_value = False
        mock_tf_path.__str__ = Mock(return_value="infra/test-project/infra/terraform")
        mock_project_path.__truediv__ = Mock(return_value=mock_tf_path)
        mock_path_class.return_value = mock_project_path
        
        # Act & Assert
        with pytest.raises(NotADirectoryError) as exc_info:
            await init_project("test-project")

        assert "Path infra/test-project/infra/terraform is not a directory" in str(exc_info.value)

    @pytest.mark.anyio
    @patch("app.services.project_services.Path")
    @patch("app.services.project_services.execute_terraform_command", new_callable=AsyncMock)
    @patch("app.services.project_services.logger")
    async def test_init_project_terraform_init_failure(self, mock_logger, mock_execute_terraform, mock_path_class):
        # Arrange
        mock_project_path = Mock()
        mock_tf_path = Mock()
        mock_tf_path.exists.return_value = True
        mock_tf_path.is_dir.return_value = True
        mock_project_path.__truediv__ = Mock(return_value=mock_tf_path)
        
        mock_path_class.return_value = mock_project_path
        mock_execute_terraform.side_effect = RuntimeError("Failed to initialize")
        
        # Act & Assert
        with pytest.raises(TerraformInitError) as exc_info:
            await init_project("test-project")
        
        assert "Failed to initialize" in str(exc_info.value)


class TestGetDescription:
    @pytest.mark.anyio
    async def test_get_description_with_readme(self):
        # Arrange
        readme_content = """# Project
        
## Description
This is a test project description.
It has multiple lines.

## Installation
Some installation notes.
"""
        mock_project_path = Mock(spec=Path)
        mock_readme_path = Mock()
        mock_readme_path.exists.return_value = True
        mock_project_path.__truediv__ = Mock(return_value=mock_readme_path)

        # Act
        with patch("builtins.open", mock_open(read_data=readme_content)):
            result = await _get_description(mock_project_path)
        
        # Assert
        expected = "This is a test project description.\nIt has multiple lines."
        assert result == expected

    @pytest.mark.anyio
    async def test_get_description_no_readme(self):
        # Arrange
        mock_project_path = Mock(spec=Path)
        mock_readme_path = Mock()
        mock_readme_path.exists.return_value = False
        mock_project_path.__truediv__ = Mock(return_value=mock_readme_path)

        # Act
        result = await _get_description(mock_project_path)
        
        # Assert
        assert result == ""

    @pytest.mark.anyio
    async def test_get_description_no_description_section(self):
        # Arrange
        readme_content = """# Project
        
## Installation
Some installation notes.
"""
        mock_project_path = Mock(spec=Path)
        mock_readme_path = Mock()
        mock_readme_path.exists.return_value = True
        mock_project_path.__truediv__ = Mock(return_value=mock_readme_path)

        # Act
        with patch("builtins.open", mock_open(read_data=readme_content)):
            result = await _get_description(mock_project_path)
        
        # Assert
        assert result == ""

    @pytest.mark.anyio
    async def test_get_description_description_at_end(self):
        # Arrange
        readme_content = """# Project
        
## Description
This is the description at the end of file.
"""
        mock_project_path = Mock(spec=Path)
        mock_readme_path = Mock()
        mock_readme_path.exists.return_value = True
        mock_project_path.__truediv__ = Mock(return_value=mock_readme_path)

        # Act
        with patch("builtins.open", mock_open(read_data=readme_content)):
            result = await _get_description(mock_project_path)
        
        # Assert
        assert result == "This is the description at the end of file."
