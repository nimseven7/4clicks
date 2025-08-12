"""API endpoints for managing task templates and task executions."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_handlers import handle_service_exceptions
from app.databases.database import get_db_session
from app.schemas.task_schema import (
    TaskCreate,
    TaskResponse,
    TaskTemplateCreate,
    TaskTemplateListResponse,
    TaskTemplateResponse,
    TaskTemplateUpdate,
)
from app.services.task_execution_service import TaskExecutionService
from app.services.task_template_service import TaskTemplateService

router = APIRouter(
    prefix="/tasks",
    tags=["Task Management"],
)

# Task Template Endpoints


@router.post("/templates", response_model=TaskTemplateResponse, status_code=201)
@handle_service_exceptions
async def create_task_template(
    template_data: TaskTemplateCreate, db: AsyncSession = Depends(get_db_session)
):
    """
    Create a new task template.

    The template file must exist in the tasks directory structure:
    - Ansible playbooks: tasks/ansible/
    - Bash scripts: tasks/scripts/

    Returns an error if the required file is not found.
    """
    service = TaskTemplateService(db)
    template = await service.create_template(template_data)
    return template


@router.get("/templates/{template_id}", response_model=TaskTemplateResponse)
@handle_service_exceptions
async def get_task_template(
    template_id: int = Path(..., description="Task template ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a task template by ID."""
    service = TaskTemplateService(db)
    return await service.get_template(template_id)


@router.put("/templates/{template_id}", response_model=TaskTemplateResponse)
@handle_service_exceptions
async def update_task_template(
    template_data: TaskTemplateUpdate,
    template_id: int = Path(..., description="Task template ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Update a task template.

    If updating file_path, the new file must exist in the tasks directory structure.
    """
    service = TaskTemplateService(db)
    template = await service.update_template(template_id, template_data)
    return template


@router.delete("/templates/{template_id}", status_code=204)
@handle_service_exceptions
async def delete_task_template(
    template_id: int = Path(..., description="Task template ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Delete a task template.

    Note: This will also delete all associated task executions.
    """
    service = TaskTemplateService(db)
    await service.delete_template(template_id)


@router.get("/templates", response_model=TaskTemplateListResponse)
@handle_service_exceptions
async def list_task_templates(
    project_name: Optional[str] = Query(None, description="Filter by project name"),
    skip: int = Query(0, ge=0, description="Number of templates to skip"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of templates to return"
    ),
    active_only: bool = Query(True, description="Return only active templates"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    List task templates.

    If project_name is provided, only templates for that project are returned.
    Otherwise, all templates are returned.
    """
    service = TaskTemplateService(db)

    if project_name:
        return await service.list_templates_by_project(
            project_name, skip=skip, limit=limit, active_only=active_only
        )
    else:
        return await service.list_all_templates(
            skip=skip, limit=limit, active_only=active_only
        )


@router.get(
    "/projects/{project_name}/templates", response_model=TaskTemplateListResponse
)
@handle_service_exceptions
async def list_project_task_templates(
    project_name: str = Path(..., description="Project name"),
    skip: int = Query(0, ge=0, description="Number of templates to skip"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of templates to return"
    ),
    active_only: bool = Query(True, description="Return only active templates"),
    db: AsyncSession = Depends(get_db_session),
):
    """List all task templates for a specific project."""
    service = TaskTemplateService(db)
    return await service.list_templates_by_project(
        project_name, skip=skip, limit=limit, active_only=active_only
    )


# Task Execution Endpoints


@router.post("/execute")
async def execute_task(
    task_data: TaskCreate,
    session: AsyncSession = Depends(get_db_session),
):
    """Create and execute a task with streaming response."""

    try:
        service = TaskExecutionService(session)
        task_execution_data = await service.prepare_task_execution(task_data)
    except Exception as err:
        # Return error immediately if task preparation fails
        error_message = str(err)  # Capture the error message in the current scope

        async def error_generator():
            yield 'data: {"status": "starting", "message": "🚀 Initializing task execution..."}\n\n'
            error_msg = f"❌ Execution failed: {error_message}"
            yield f'data: {{"status": "error", "message": "{error_msg}"}}\n\n'

        return StreamingResponse(
            error_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            },
        )

    async def generate():
        try:
            yield 'data: {"status": "starting", "message": "🚀 Initializing task execution..."}\n\n'

            # Create a new service instance for streaming (no session needed)
            async for log_chunk in TaskExecutionService.execute_task_streaming_static(
                task_execution_data
            ):
                yield log_chunk

            yield 'data: {"status": "stream_end", "message": "Stream completed"}\n\n'
            # mark the task as completed
            await service.mark_task_as_completed(task_execution_data)

        except Exception as e:
            error_msg = f"❌ Execution failed: {str(e)}"
            yield f'data: {{"status": "error", "message": "{error_msg}"}}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


@router.get("/executions/{task_id}", response_model=TaskResponse)
@handle_service_exceptions
async def get_task_execution(
    task_id: int = Path(..., description="Task execution ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get details of a specific task execution."""
    service = TaskExecutionService(db)
    return await service.get_task(task_id)


@router.get("/projects/{project_name}/executions")
@handle_service_exceptions
async def list_project_task_executions(
    project_name: str = Path(..., description="Project name"),
    workspace_name: Optional[str] = Query(None, description="Workspace name filter"),
    skip: int = Query(0, ge=0, description="Number of executions to skip"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of executions to return"
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """List all task executions for a specific project."""
    service = TaskExecutionService(db)
    tasks = await service.list_tasks_by_project(
        project_name, workspace_name=workspace_name, skip=skip, limit=limit
    )

    return {
        "tasks": tasks,
        "total": len(tasks),
        "skip": skip,
        "limit": limit,
    }
