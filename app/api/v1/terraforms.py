from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.params import ProjectWorkspaceParams
from app.databases.database import get_db_session
from app.logger import logger
from app.services.inventory_services import InventoryService
from app.services.terraform_services import (
    build_var_file,
    get_var_file,
    stream_terraform_apply,
    stream_terraform_destroy,
    stream_terraform_plan,
)
from app.services.variable_services import VariableService

router = APIRouter(
    prefix="/projects/{project}/workspaces/{workspace}", tags=["Terraform"]
)


async def cleanup_inventory_background(project: str, workspace: str):
    """
    Background task to cleanup inventory after successful terraform destroy.
    """
    import asyncio

    try:
        # Wait a short moment to ensure terraform has fully completed
        await asyncio.sleep(2)

        logger.info(
            f"Starting background inventory cleanup for project: {project}, workspace: {workspace}"
        )

        # Import here to avoid circular imports
        from app.databases.database import get_database_manager

        # Create a new database session for the background task
        db_manager = get_database_manager()
        async with db_manager.get_session() as db:
            inventory_service = InventoryService(db)
            deleted_count = await inventory_service.cleanup_workspace_inventory(
                project, workspace
            )

            logger.info(
                f"Background inventory cleanup completed successfully for {project}/{workspace}. "
                f"Deleted {deleted_count} inventory items."
            )

    except Exception as e:
        logger.error(
            f"Background inventory cleanup failed for {project}/{workspace}: {str(e)}",
            exc_info=True,
        )


async def sync_inventory_background(project: str, workspace: str):
    """
    Background task to sync inventory after successful terraform apply.
    """
    # TODO: Move this to a proper background task manager
    import asyncio

    try:
        # Wait a short moment to ensure terraform has fully completed
        await asyncio.sleep(2)

        logger.info(
            f"Starting background inventory sync for project: {project}, workspace: {workspace}"
        )

        # Import here to avoid circular imports
        from app.databases.database import get_database_manager

        # Create a new database session for the background task
        db_manager = get_database_manager()
        async with db_manager.get_session() as db:
            inventory_service = InventoryService(db)
            result = await inventory_service.sync_from_terraform_outputs(
                project, workspace
            )

            logger.info(
                f"Background inventory sync completed successfully for {project}/{workspace}. "
                f"Processed: {result.items_processed}, Created: {result.items_created}, "
                f"Updated: {result.items_updated}, IPs created: {result.ips_created}, "
                f"IPs updated: {result.ips_updated}"
            )

            if result.errors:
                logger.warning(
                    f"Inventory sync had {len(result.errors)} errors: {result.errors}"
                )
            else:
                logger.info(
                    f"Inventory sync completed without errors for {project}/{workspace}"
                )

    except Exception as e:
        logger.error(
            f"Background inventory sync failed for {project}/{workspace}: {str(e)}",
            exc_info=True,
        )


@router.post(
    "/plan",
    responses={
        400: {
            "description": "Bad Request: Cannot provide variables and fetch from database at the same time."
        }
    },
)
async def plan(
    variables: dict[str, str | int | float | bool] | None = None,
    from_db: bool = Query(True, description="Fetch variables from the database"),
    params: ProjectWorkspaceParams = Depends(),
    db: AsyncSession = Depends(get_db_session),
):
    # Pre-validate that var file exists if no variables provided
    if not variables:
        try:
            variable_service = VariableService(db)
            project_path = Path(f"infra/{params.project}/infra/terraform")
            if from_db:
                # If fetching from the database, build the var file
                await build_var_file(params.project, params.workspace, variable_service)
            else:
                await get_var_file(project_path, params.workspace)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Var file not found")

    if variables and from_db:
        raise HTTPException(
            status_code=400,
            detail="Cannot provide variables and fetch from database at the same time. "
            "Please either provide variables or set from_db=False.",
        )

    async def safe_terraform_stream():
        """
        Wrapper for terraform streaming that handles RuntimeError exceptions
        and converts them to proper error responses.
        """
        try:
            async for line in stream_terraform_plan(
                Path(f"infra/{params.project}/infra/terraform"),
                params.workspace,
                vars=variables,
            ):
                yield line
        except RuntimeError as e:
            # If a RuntimeError occurs during streaming, yield an error message
            # Since we can't change the HTTP status code once streaming has started,
            # we'll yield a clear error message
            error_message = f"\n\nERROR: {str(e)}\n"
            yield error_message

    return StreamingResponse(
        safe_terraform_stream(),
        media_type="text/plain",
    )


@router.post(
    "/apply",
    responses={
        400: {
            "description": "Bad Request: Cannot provide variables and fetch from database at the same time."
        }
    },
)
async def apply(
    background_tasks: BackgroundTasks,
    variables: dict[str, str | int | float | bool] | None = None,
    from_db: bool = Query(True, description="Fetch variables from the database"),
    params: ProjectWorkspaceParams = Depends(),
    db: AsyncSession = Depends(get_db_session),
):
    if not variables:
        try:
            variable_service = VariableService(db)
            project_path = Path(f"infra/{params.project}/infra/terraform")
            if from_db:
                # If fetching from the database, build the var file
                await build_var_file(params.project, params.workspace, variable_service)
            else:
                await get_var_file(project_path, params.workspace)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="Var file not found. Perhaps you should go for a /plan first?",
            )

    if variables and from_db:
        raise HTTPException(
            status_code=400,
            detail="Cannot provide variables and fetch from database at the same time. "
            "Please either provide variables or set from_db=False.",
        )

    async def safe_terraform_stream():
        """
        Wrapper for terraform streaming that handles RuntimeError exceptions.
        """
        apply_successful = False
        try:
            async for line in stream_terraform_apply(
                Path(f"infra/{params.project}/infra/terraform"),
                params.workspace,
                vars=variables,
            ):
                yield line

                # Check for successful apply completion - multiple possible success indicators
                if any(
                    success_phrase in line
                    for success_phrase in [
                        "Apply complete!",
                        "Apply successful!",
                        "Terraform has completed the apply",
                        "has been successfully applied",
                    ]
                ):
                    apply_successful = True
                    logger.info(
                        f"Terraform apply completed successfully for {params.project}/{params.workspace}"
                    )
                    logger.debug(f"Success detected from line: {line.strip()}")

        except RuntimeError as e:
            error_message = f"\n\nERROR: {str(e)}\n"
            yield error_message

        # Schedule inventory sync if apply was successful
        if apply_successful:
            background_tasks.add_task(
                sync_inventory_background, params.project, params.workspace
            )
            logger.info(
                f"Scheduled background inventory sync for {params.project}/{params.workspace}"
            )

    return StreamingResponse(
        safe_terraform_stream(),
        media_type="text/plain",
    )


@router.post("/destroy")
async def destroy(
    background_tasks: BackgroundTasks,
    variables: dict[str, str | int | float | bool] | None = None,
    params: ProjectWorkspaceParams = Depends(),
):
    async def safe_terraform_stream():
        """
        Wrapper for terraform streaming that handles RuntimeError exceptions.
        """
        destroy_successful = False
        try:
            async for line in stream_terraform_destroy(
                Path(f"infra/{params.project}/infra/terraform"),
                params.workspace,
                vars=variables,
            ):
                yield line
                # Check for successful completion indicators
                if (
                    "Destroy complete!" in line
                    or ("Resources:" in line and "destroyed" in line)
                    or "Apply complete!" in line  # In case of empty state
                ):
                    destroy_successful = True
                    logger.info(
                        f"Terraform destroy completed successfully for {params.project}/{params.workspace}"
                    )
        except RuntimeError as e:
            error_message = f"\n\nERROR: {str(e)}\n"
            yield error_message
            logger.error(
                f"Terraform destroy failed for {params.project}/{params.workspace}: {str(e)}"
            )

        # Schedule inventory cleanup if destroy was successful
        if destroy_successful:
            background_tasks.add_task(
                cleanup_inventory_background, params.project, params.workspace
            )
            logger.info(
                f"Scheduled background inventory cleanup for {params.project}/{params.workspace}"
            )
        else:
            logger.warning(
                f"Terraform destroy may not have completed successfully for {params.project}/{params.workspace}, "
                "skipping inventory cleanup"
            )

    return StreamingResponse(
        safe_terraform_stream(),
        media_type="text/plain",
    )
