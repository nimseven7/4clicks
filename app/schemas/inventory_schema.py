from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IPAddressBase(BaseModel):
    ip: str = Field(..., max_length=45, description="IP address (IPv4 or IPv6)")
    description: Optional[str] = Field(None, description="Optional description")
    workspace: Optional[str] = Field(
        None, max_length=255, description="Optional workspace name"
    )


class IPAddressCreate(IPAddressBase):
    pass


class IPAddressResponse(IPAddressBase):
    id: int
    deployment_date: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InventoryBase(BaseModel):
    name: str = Field(..., max_length=255, description="Name of the inventory")
    project_name: str = Field(..., max_length=255, description="Name of the project")
    workspace_name: Optional[str] = Field(
        None, max_length=255, description="Name of the workspace (optional)"
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="Optional description of the inventory"
    )
    metadata_: Optional[Dict[str, Any]] = Field(
        None, description="Optional metadata about the inventory", alias="metadata"
    )


class InventoryCreate(InventoryBase):
    pass


class InventoryResponse(InventoryBase):
    id: int
    deployment_date: datetime
    created_at: datetime
    updated_at: datetime
    ip_addresses: List[IPAddressResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class InventoryUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata")


class TerraformSyncRequest(BaseModel):
    """Request model for syncing inventory from Terraform outputs."""

    project_name: str = Field(..., description="Name of the project")
    workspace_name: Optional[str] = Field(None, description="Name of the workspace")


class TerraformSyncResponse(BaseModel):
    """Response model for Terraform sync operation."""

    project_name: str
    workspace_name: Optional[str]
    items_processed: int
    items_created: int
    items_updated: int
    ips_created: int
    ips_updated: int
    created_inventories: List[str] = Field(default_factory=list)
    updated_inventories: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
