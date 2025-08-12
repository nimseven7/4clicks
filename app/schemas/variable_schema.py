"""Pydantic schemas for variables."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.databases.models import VariableType


class VariableBase(BaseModel):
    """Base schema for variables."""

    key: str = Field(..., description="Variable key/name")
    value: Any = Field(..., description="Variable value")
    description: Optional[str] = Field(None, description="Variable description")
    variable_type: VariableType = Field(
        VariableType.TERRAFORM,
        description="Variable type (string, number, bool, list, object)",
    )
    is_sensitive: bool = Field(False, description="Whether the variable is sensitive")


class VariableCreate(VariableBase):
    """Schema for creating a variable."""

    project_name: str = Field(..., description="Project name")
    workspace_name: Optional[str] = Field(None, description="Workspace name (optional)")


class VariableUpdate(BaseModel):
    """Schema for updating a variable."""

    key: Optional[str] = Field(None, description="Variable key/name")
    value: Optional[Any] = Field(None, description="Variable value")
    description: Optional[str] = Field(None, description="Variable description")
    variable_type: Optional[VariableType] = Field(None, description="Variable type")
    is_sensitive: Optional[bool] = Field(
        None, description="Whether the variable is sensitive"
    )
    project_name: Optional[str] = Field(None, description="Project name")
    workspace_name: Optional[str] = Field(None, description="Workspace name")


class VariableResponse(VariableBase):
    """Schema for variable response."""

    id: int
    project_name: str
    workspace_name: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VariableListResponse(BaseModel):
    """Response schema for variable lists."""

    variables: list[VariableResponse]
    total: int


class VariableBulkImportRequest(BaseModel):
    """Schema for bulk import request."""

    variables: list[VariableCreate]
    overwrite_existing: bool = Field(
        False, description="Whether to overwrite existing variables"
    )


class VariableBulkImportResponse(BaseModel):
    """Schema for bulk import response."""

    created: int
    updated: int
    errors: list[str]
    created_variables: list[VariableResponse]
    updated_variables: list[VariableResponse]


class VariableExportResponse(BaseModel):
    """Schema for variable export response."""

    terraform_vars: dict[str, Any]
    env_vars: dict[str, Any]
    sensitive_vars_excluded: list[str]
    total_variables: int


class VariableValidationResponse(BaseModel):
    """Schema for variable validation response."""

    total_variables: int
    required_variables: int
    missing_variables: list[str]
    extra_variables: list[str]
    sensitive_variables_count: int
    validation_passed: bool


class VariableStatisticsResponse(BaseModel):
    """Schema for variable statistics response."""

    total_variables: int
    projects: int
    workspaces: int
    sensitive_variables: int
    variable_types: dict[str, int]
    variables_by_project: dict[str, int]
    variables_by_workspace: dict[str, int]


class VariableShellImportRequest(BaseModel):
    """Schema for importing variables from shell script content."""

    shell_content: str = Field(
        ..., description="Shell script content with export statements"
    )
    project_name: str = Field(..., description="Project name for the variables")
    variable_type: VariableType = Field(
        ..., description="Type of variables (PROJECT or INSTANCE)"
    )
    workspace_name: Optional[str] = Field(
        None, description="Workspace name (required for INSTANCE variables)"
    )
    comment_description: Optional[str] = Field(
        None, description="Default description for variables without comments"
    )
    overwrite_existing: bool = Field(
        False, description="Whether to overwrite existing variables"
    )


class VariableShellImportResponse(BaseModel):
    """Schema for shell script import response."""

    parsed_variables: int
    created: int
    updated: int
    skipped: int
    errors: list[str]
    created_variables: list[VariableResponse]
    updated_variables: list[VariableResponse]
