"""
Tests for terraform API endpoints.
"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.api.v1.terraforms import router


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class MockAsyncGenerator:
    """Mock async generator for testing streaming responses."""
    
    def __init__(self, items, raise_error_after=None):
        self.items = items
        self.raise_error_after = raise_error_after
        self.yielded_count = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.yielded_count >= len(self.items):
            raise StopAsyncIteration
        
        if self.raise_error_after is not None and self.yielded_count >= self.raise_error_after:
            raise RuntimeError("Terraform error detected in stream")
        
        item = self.items[self.yielded_count]
        self.yielded_count += 1
        return item


@pytest.mark.asyncio
class TestTerraformPlanAPI:
    """Tests for the /plan endpoint."""

    @patch("app.api.v1.terraforms.stream_terraform_plan")
    @patch("app.api.v1.terraforms.get_var_file")
    @patch("app.api.v1.terraforms.get_db_session")
    async def test_plan_successful_stream(self, mock_db, mock_get_var_file, mock_stream_plan):
        """Test successful terraform plan streaming."""
        # Mock the var file to exist
        mock_get_var_file.return_value = Path("/test/tfvars.d/test.tfvars.json")
        
        # Mock successful streaming
        mock_stream_plan.return_value = MockAsyncGenerator([
            "Initializing the backend...\n",
            "Terraform will perform the following actions:\n",
            "Plan: 1 to add, 0 to change, 0 to destroy.\n"
        ])
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/projects/test-project/workspaces/test/plan")
        
        assert response.status_code == 200
        assert "Initializing the backend" in response.text
        assert "Plan: 1 to add" in response.text

    @patch("app.api.v1.terraforms.stream_terraform_plan")
    @patch("app.api.v1.terraforms.get_var_file")
    @patch("app.api.v1.terraforms.get_db_session")
    async def test_plan_with_error_in_stream(self, mock_db, mock_get_var_file, mock_stream_plan):
        """Test terraform plan with error occurring during streaming."""
        # Mock the var file to exist
        mock_get_var_file.return_value = Path("/test/tfvars.d/test.tfvars.json")
        
        # Mock streaming that raises an error after yielding some output
        mock_stream_plan.return_value = MockAsyncGenerator([
            "Initializing the backend...\n",
            "Terraform will perform the following actions:\n",
        ], raise_error_after=2)
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/projects/test-project/workspaces/test/plan")
        
        # Should still return 200 because streaming has started
        assert response.status_code == 200
        # Should contain the partial output and the error message
        assert "Initializing the backend" in response.text
        assert "ERROR: Terraform error detected in stream" in response.text

    @patch("app.api.v1.terraforms.get_var_file")
    @patch("app.api.v1.terraforms.get_db_session")
    async def test_plan_var_file_not_found(self, mock_db, mock_get_var_file):
        """Test terraform plan when var file is not found."""
        # Mock the var file to not exist
        mock_get_var_file.side_effect = FileNotFoundError("Var file does not exist")
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/projects/test-project/workspaces/test/plan")
        
        assert response.status_code == 404
        assert "Var file not found" in response.json()["detail"]

    @patch("app.api.v1.terraforms.stream_terraform_plan")
    @patch("app.api.v1.terraforms.get_var_file")
    @patch("app.api.v1.terraforms.get_db_session")
    async def test_plan_with_variables(self, mock_db, mock_get_var_file, mock_stream_plan):
        """Test terraform plan with variables provided."""
        # Mock successful streaming
        mock_stream_plan.return_value = MockAsyncGenerator([
            "Initializing the backend...\n",
            "Plan: 1 to add, 0 to change, 0 to destroy.\n"
        ])
        
        variables = {"key1": "value1", "key2": 42}
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/projects/test-project/workspaces/test/plan",
                json=variables
            )
        
        assert response.status_code == 200
        assert "Plan: 1 to add" in response.text
        # Should not call get_var_file when variables are provided
        mock_get_var_file.assert_not_called()


@pytest.mark.asyncio
class TestTerraformApplyAPI:
    """Tests for the /apply endpoint."""

    @patch("app.api.v1.terraforms.stream_terraform_apply")
    async def test_apply_with_error_in_stream(self, mock_stream_apply):
        """Test terraform apply with error occurring during streaming."""
        # Mock streaming that raises an error
        mock_stream_apply.return_value = MockAsyncGenerator([
            "Applying terraform...\n",
        ], raise_error_after=1)
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/projects/test-project/workspaces/test/apply")
        
        # Should still return 200 because streaming has started
        assert response.status_code == 200
        # Should contain the error message
        assert "ERROR: Terraform error detected in stream" in response.text


@pytest.mark.asyncio
class TestTerraformDestroyAPI:
    """Tests for the /destroy endpoint."""

    @patch("app.api.v1.terraforms.stream_terraform_destroy")
    async def test_destroy_with_error_in_stream(self, mock_stream_destroy):
        """Test terraform destroy with error occurring during streaming."""
        # Mock streaming that raises an error
        mock_stream_destroy.return_value = MockAsyncGenerator([
            "Destroying terraform resources...\n",
        ], raise_error_after=1)
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/projects/test-project/workspaces/test/destroy")
        
        # Should still return 200 because streaming has started
        assert response.status_code == 200
        # Should contain the error message
        assert "ERROR: Terraform error detected in stream" in response.text
