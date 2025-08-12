"""Schemas for task management."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.databases.models import SSHKeyType, TaskStatus, TaskTemplateType


class TaskTemplateBase(BaseModel):
    """Base schema for task template."""

    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    template_type: TaskTemplateType = Field(
        ..., description="Template type (ansible or bash)"
    )
    file_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="File path relative to tasks folder",
    )
    project_name: str = Field(
        ..., min_length=1, max_length=255, description="Associated project name"
    )
    parameters_schema: Optional[Dict[str, Any]] = Field(
        None, description="Optional parameters schema"
    )
    is_active: bool = Field(True, description="Whether the template is active")


class TaskTemplateCreate(TaskTemplateBase):
    """Schema for creating a task template."""

    pass


class TaskTemplateUpdate(BaseModel):
    """Schema for updating a task template."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Template name"
    )
    description: Optional[str] = Field(None, description="Template description")
    template_type: Optional[TaskTemplateType] = Field(
        None, description="Template type (ansible or bash)"
    )
    file_path: Optional[str] = Field(
        None,
        min_length=1,
        max_length=500,
        description="File path relative to tasks folder",
    )
    parameters_schema: Optional[Dict[str, Any]] = Field(
        None, description="Optional parameters schema"
    )
    is_active: Optional[bool] = Field(
        None, description="Whether the template is active"
    )


class TaskTemplateResponse(TaskTemplateBase):
    """Schema for task template response."""

    id: int = Field(..., description="Template ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class TaskTemplateListResponse(BaseModel):
    """Schema for task template list response."""

    templates: List[TaskTemplateResponse] = Field(
        ..., description="List of task templates"
    )
    total: int = Field(..., description="Total number of templates")


# SSH Key Management Schemas


class SSHKeyPairBase(BaseModel):
    """Base schema for SSH key pair."""

    name: str = Field(..., min_length=1, max_length=255, description="Key pair name")
    description: Optional[str] = Field(None, description="Key pair description")
    project_name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Associated project name"
    )
    passphrase_hint: Optional[str] = Field(
        None, max_length=255, description="Optional passphrase hint"
    )


class SSHKeyPairGenerate(SSHKeyPairBase):
    """Schema for generating a new SSH key pair."""

    key_type: SSHKeyType = Field(SSHKeyType.ED25519, description="SSH key type")
    key_size: Optional[int] = Field(
        None, description="Key size for RSA keys (2048, 3072, 4096)"
    )
    passphrase: Optional[str] = Field(None, description="Optional passphrase")


class SSHKeyPairImport(SSHKeyPairBase):
    """Schema for importing an existing SSH key pair."""

    private_key: str = Field(..., description="Private key content")
    public_key: Optional[str] = Field(
        None, description="Public key content (auto-derived if not provided)"
    )
    passphrase: Optional[str] = Field(
        None, description="Passphrase if private key is encrypted"
    )


class SSHKeyPairUpdate(BaseModel):
    """Schema for updating an SSH key pair."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Key pair name"
    )
    description: Optional[str] = Field(None, description="Key pair description")
    is_active: Optional[bool] = Field(None, description="Whether the key is active")
    passphrase_hint: Optional[str] = Field(
        None, max_length=255, description="Optional passphrase hint"
    )


class SSHKeyPairResponse(SSHKeyPairBase):
    """Schema for SSH key pair response."""

    id: int = Field(..., description="Key pair ID")
    key_type: SSHKeyType = Field(..., description="SSH key type")
    key_size: Optional[int] = Field(None, description="Key size for RSA keys")
    fingerprint: str = Field(..., description="Key fingerprint")
    public_key: str = Field(..., description="Public key content")
    is_active: bool = Field(..., description="Whether the key is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")

    class Config:
        from_attributes = True


class SSHKeyPairListResponse(BaseModel):
    """Schema for SSH key pair list response."""

    ssh_keys: List[SSHKeyPairResponse] = Field(..., description="List of SSH key pairs")
    total: int = Field(..., description="Total number of SSH key pairs")


class SSHPublicKeyResponse(BaseModel):
    """Schema for public key export response."""

    public_key: str = Field(..., description="Public key content")
    fingerprint: str = Field(..., description="Key fingerprint")
    key_type: SSHKeyType = Field(..., description="SSH key type")


class TaskBase(BaseModel):
    """Base schema for task."""

    name: str = Field(..., min_length=1, max_length=255, description="Task name")
    description: Optional[str] = Field(None, description="Task description")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Task parameters")
    project_name: str = Field(
        ..., min_length=1, max_length=255, description="Associated project name"
    )
    workspace_name: Optional[str] = Field(
        None, max_length=255, description="Associated workspace name"
    )


class TaskCreate(TaskBase):
    """Schema for creating a task execution."""

    template_id: int = Field(..., description="Task template ID")
    ssh_key_id: Optional[int] = Field(
        None, description="SSH key pair ID for authentication"
    )
    target_ip_addresses: Optional[List[int]] = Field(
        None, description="Target IP address IDs"
    )
    target_inventories: Optional[List[int]] = Field(
        None, description="Target inventory IDs"
    )


class TaskResponse(TaskBase):
    """Schema for task response."""

    id: int = Field(..., description="Task ID")
    status: TaskStatus = Field(..., description="Task execution status")
    logs: Optional[str] = Field(None, description="Execution logs")
    exit_code: Optional[int] = Field(None, description="Exit code from execution")
    started_at: Optional[datetime] = Field(None, description="Start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    template_id: int = Field(..., description="Task template ID")
    template: TaskTemplateResponse = Field(..., description="Associated task template")
    ssh_key_id: Optional[int] = Field(None, description="SSH key pair ID")
    ssh_key: Optional[SSHKeyPairResponse] = Field(
        None, description="Associated SSH key pair"
    )

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Schema for task list response."""

    tasks: List[TaskResponse] = Field(..., description="List of tasks")
    total: int = Field(..., description="Total number of tasks")
