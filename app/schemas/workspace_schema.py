from pydantic import BaseModel, Field

from app.schemas import ProjectOutput
from app.var_type import TFVars


class WorkspaceOutput(BaseModel):
    name: str
    active: bool


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceOutput]


class WorkspaceCreateInput(BaseModel):
    name: str = Field(
        ..., description="Name of the workspace", pattern="^[A-Za-z0-9_-]+$"
    )


class WorkspaceWithVarsDetailResponse(BaseModel):
    name: str
    project: ProjectOutput
    tfvars: TFVars = TFVars()


class DeploymentVarsResponse(BaseModel):
    """Response schema for deployment variables in shell script format."""

    content: str = Field(
        ..., description="Shell script content with exported variables"
    )
