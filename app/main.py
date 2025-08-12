import os
from contextlib import asynccontextmanager
from typing import cast

import fastapi
# import fastapi_swagger_dark as fsd  # type: ignore

from app.api.v1 import (
    inventory,
    projects,
    ssh_keys,
    tasks,
    terraforms,
    variables,
    workspaces,
)
from app.databases.database import get_database_manager, init_database
from app.logger import logger

stage = os.getenv("STAGE", "dev")


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    """Application lifespan manager for startup and shutdown."""
    # Startup
    database_url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/4clicks-dev"
    )

    try:
        # Initialize database
        db_manager = init_database(database_url)
        logger.info("Database initialized successfully")

        # Create tables (in production, use Alembic migrations instead)
        # if stage == "dev":
        #     await db_manager.create_tables()
        #     logger.info("Database tables created")

        yield

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        # Shutdown
        try:
            db_manager = get_database_manager()
            await db_manager.close()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database: {e}")


# async def _swagger_dark_ui_html(
#     request: fastapi.Request,
#     # _docs_auth: typing.Annotated[None, fastapi.Depends(auth_validation)],
# ) -> fastapi.responses.HTMLResponse:
#     """Serve the Swagger UI HTML page."""
#     return cast(fastapi.responses.HTMLResponse, fsd.get_swagger_ui_html(request))


app = fastapi.FastAPI(
    title="4-clicks deploy",
    description="""
An API to deploy a web app or platform using Terraform. 
This API provides endpoints to manage Terraform projects, 
workspaces, and operations like plan, apply, and destroy.
It includes listing projects, initializing them, and retrieving details.""",
    version="0.1.0",
    debug=stage == "dev",
    root_path_in_servers=False,
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Projects",
            "description": "Manage Terraform projects.",
        },
        {
            "name": "Workspaces",
            "description": "Manage Terraform workspaces within projects.",
        },
        {
            "name": "Variables",
            "description": """Manage Terraform variables for projects and workspaces"""
            """ directly from this API Endpoint.""",
        },
        {
            "name": "Terraform",
            "description": "Perform Terraform operations like plan, apply, "
            "and destroy with variables.",
        },
        {
            "name": "Inventory",
            "description": "Retrieve inventory information for projects.",
        },
        {
            "name": "Task Management",
            "description": "Manage task templates and execute tasks on inventories.",
        },
        {
            "name": "SSH Key Management",
            "description": "Generate and import SSH key pairs for secure access.",
        },
    ],
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",  # comment this if you want the dark mode swagger
    # docs_url=None,
    redoc_url="/api/redoc",
)

# app.get("/api/docs", include_in_schema=False)(_swagger_dark_ui_html)
# app.get("/api/dark_theme.css", include_in_schema=False, name="dark_theme")(
#     fsd.dark_swagger_theme
# )

# TERRAFORM_DIR = "./infra/terraform"


app.include_router(projects.router, prefix="/api/v1")
app.include_router(workspaces.router, prefix="/api/v1")
app.include_router(variables.router, prefix="/api/v1")
app.include_router(terraforms.router, prefix="/api/v1")
app.include_router(inventory.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(ssh_keys.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint to check if the API is running.
    Returns a simple message with the app title."""
    return {"message": f"Hello from {app.title}!"}
