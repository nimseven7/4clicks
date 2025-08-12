from pydantic import BaseModel

from app.var_type import TFVars


class ProjectOutput(BaseModel):
    name: str
    description: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectOutput]


class ProjectDetailResponse(BaseModel):
    project: ProjectOutput
    tfvars: TFVars = TFVars()
