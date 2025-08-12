from fastapi import Path


class ProjectParams:
    def __init__(
        self,
        project: str = Path(
            ...,
            pattern="^[A-Za-z0-9_-]+$",
            description="Project name (letters, numbers, - or _)",
        ),
    ):
        self.project = project


class ProjectWorkspaceParams:
    """Parameters for project and workspace operations.
    This class is used to validate and parse the project and workspace names
    from the request path parameters.
    contains:
    - project: The name of the project, must match the pattern `^[A-Za-z0-9_-]+$`.
    - workspace: The name of the workspace, must match the pattern `^[A-Za-z0-9_-]+$`.
    """

    def __init__(
        self,
        project: str = Path(
            ...,
            pattern="^[A-Za-z0-9_-]+$",
            description="Project name (letters, numbers, - or _)",
        ),
        workspace: str = Path(
            ...,
            pattern="^[A-Za-z0-9_-]+$",
            description="Workspace name (letters, numbers, - or _)",
        ),
    ):
        self.project = project
        self.workspace = workspace
