"""Service layer for variable management with comprehensive use cases."""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.models import Variable, VariableType
from app.logger import logger
from app.repositories.variable_repository import VariableRepository
from app.schemas.variable_schema import VariableCreate, VariableResponse, VariableUpdate


class VariableService:
    """Service for managing Terraform variables with comprehensive use cases."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = VariableRepository(session)

    async def create_variable(self, variable_data: VariableCreate) -> Variable:
        """Create a new variable with validation."""
        # Check if variable already exists
        existing = await self.repository.get_by_key_and_project(
            variable_data.key, variable_data.project_name, variable_data.workspace_name
        )

        if existing:
            raise ValueError(
                f"Variable '{variable_data.key}' already exists for project "
                f"'{variable_data.project_name}' and workspace '{variable_data.workspace_name}'"  # noqa: E501
            )

        variable = await self.repository.create_from_schema(variable_data)
        try:
            await self.session.flush()  # Persist without committing
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to create variable: {e}")
            raise

        logger.info(
            f"Creating variable '{variable.key}' for project '{variable.project_name}'"
            f"{f' workspace {variable.workspace_name}' if variable.workspace_name else ''}"  # noqa: E501
        )
        return variable

    async def get_variable(self, variable_id: int) -> Optional[Variable]:
        """Get a variable by ID."""
        return await self.repository.get_by_id(variable_id)

    async def get_variable_by_key(
        self, key: str, project_name: str, workspace_name: Optional[str] = None
    ) -> Optional[Variable]:
        """Get a variable by key, project, and workspace."""
        return await self.repository.get_by_key_and_project(
            key, project_name, workspace_name
        )

    async def get_variables_by_project(
        self,
        project_name: str,
        workspace_name: Optional[str] = None,
        variable_type: VariableType = VariableType.TERRAFORM,
        skip: int = 0,
        limit: int = 100,
    ) -> List[VariableResponse]:
        """Get all variables for a project and workspace."""
        variables = await self.repository.list_by_project(
            project_name,
            skip=skip,
            limit=limit,
            workspace_name=workspace_name,
            variable_type=variable_type,
        )
        return [VariableResponse.model_validate(var) for var in variables]

    async def update_variable(
        self, variable_id: int, variable_data: VariableUpdate
    ) -> Optional[Variable]:
        """Update a variable."""
        try:
            variable = await self.repository.update_from_schema(
                variable_id, variable_data
            )
            await self.session.flush()  # Ensure changes are saved
            logger.info(f"Updated variable ID {variable_id}")
            return variable
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update variable ID {variable_id}: {e}")
            raise

    async def delete_variable(self, variable_id: int) -> bool:
        """Delete a variable."""
        try:
            success = await self.repository.delete(variable_id)
            if success:
                logger.info(f"Deleted variable ID {variable_id}")
            return success
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete variable ID {variable_id}: {e}")
            raise

    async def list_all_variables(
        self,
        skip: int = 0,
        limit: int = 100,
        project_filter: Optional[str] = None,
        workspace_filter: Optional[str] = None,
        variable_type_filter: Optional[VariableType] = None,
    ) -> List[VariableResponse]:
        """List all variables with optional filtering."""
        variables = await self.repository.list_all(
            skip, limit, project_filter, workspace_filter, variable_type_filter
        )
        return [VariableResponse.model_validate(var) for var in variables]

    async def search_variables(
        self,
        search_term: str,
        project_name: Optional[str] = None,
        workspace_name: Optional[str] = None,
        variable_type: Optional[VariableType] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Variable]:
        """Search variables by key or description."""
        return await self.repository.search_variables(
            search_term, project_name, workspace_name, variable_type, skip, limit
        )

    # === Use Case Examples ===

    async def bulk_import_variables(
        self, variables_data: List[VariableCreate], overwrite_existing: bool = False
    ) -> Dict[str, Any]:
        """
        Bulk import variables with conflict resolution.

        Use case: Import variables from a configuration file or another environment.
        """
        created = []
        updated = []
        errors = []

        for var_data in variables_data:
            try:
                existing = await self.repository.get_by_key_and_project(
                    var_data.key, var_data.project_name, var_data.workspace_name
                )

                if existing and not overwrite_existing:
                    errors.append(f"Variable '{var_data.key}' already exists (skipped)")
                elif existing and overwrite_existing:
                    # Update existing variable
                    update_data = VariableUpdate(**var_data.model_dump())
                    variable = await self.repository.update_from_schema(
                        existing.id, update_data
                    )
                    updated.append(variable)
                else:
                    # Create new variable
                    variable = await self.repository.create_from_schema(var_data)
                    created.append(variable)

            except Exception as e:
                errors.append(f"Error processing '{var_data.key}': {str(e)}")

        await self.session.flush()  # Ensure all changes are saved
        logger.info(
            f"Bulk import completed: {len(created)} created, {len(updated)} updated, "
            f"{len(errors)} errors"
        )

        return {
            "created": len(created),
            "updated": len(updated),
            "errors": errors,
            "created_variables": created,
            "updated_variables": updated,
        }

    async def clone_workspace_variables(
        self,
        source_project: str,
        source_workspace: str,
        target_project: str,
        target_workspace: str,
        variable_type: VariableType = VariableType.TERRAFORM,
        overwrite_existing: bool = False,
    ) -> Dict[str, Any]:
        """
        Clone variables from one workspace to another.

        Use case: Copy variables when creating a new environment or workspace.
        """
        source_variables = await self.repository.list_by_project(
            source_project, workspace_name=source_workspace, variable_type=variable_type
        )

        if not source_variables:
            return {"message": "No variables found in source workspace", "cloned": 0}

        cloned_data = []
        for var in source_variables:
            var_data = VariableCreate(
                key=var.key,
                value=var.value,
                description=var.description,
                variable_type=var.variable_type,
                is_sensitive=var.is_sensitive,
                project_name=target_project,
                workspace_name=target_workspace,
            )
            cloned_data.append(var_data)

        result = await self.bulk_import_variables(cloned_data, overwrite_existing)
        result["source_variables_count"] = len(source_variables)

        await self.session.flush()  # Ensure all changes are saved

        logger.info(
            f"Cloned {result['created']} variables from {source_project}/{source_workspace} "  # noqa: E501
            f"to {target_project}/{target_workspace}"
        )

        return result

    async def cleanup_workspace_variables(
        self, project_name: str, workspace_name: Optional[str] = None
    ) -> int:
        """
        Clean up all variables for a workspace.

        Use case: Remove all variables when a workspace is deleted.
        """
        deleted_count = await self.repository.delete_by_project(
            project_name, workspace_name
        )
        logger.info(
            f"Cleaned up {deleted_count} variables for project '{project_name}'"
            f"{f' workspace {workspace_name}' if workspace_name else ''}"
        )
        await self.session.flush()  # Ensure all changes are saved
        return deleted_count

    async def export_variables_to_terraform_format(
        self,
        project_name: str,
        workspace_name: Optional[str] = None,
        include_sensitive: bool = False,
    ) -> Dict[str, Any]:
        """
        Export variables in Terraform-compatible format.

        Use case: Generate terraform.tfvars file or environment variables.
        """
        variables = await self.repository.list_by_project(
            project_name, workspace_name=workspace_name
        )

        terraform_vars = {}
        env_vars = {}
        sensitive_vars = []

        for var in variables:
            if var.is_sensitive and not include_sensitive:
                sensitive_vars.append(var.key)
                continue

            # Terraform variables format
            terraform_vars[var.key] = var.value

            # Environment variables format (TF_VAR_<name>)
            env_vars[f"TF_VAR_{var.key}"] = var.value

        return {
            "terraform_vars": terraform_vars,
            "env_vars": env_vars,
            "sensitive_vars_excluded": sensitive_vars,
            "total_variables": len(variables),
        }

    async def validate_variable_references(
        self,
        project_name: str,
        workspace_name: Optional[str] = None,
        required_variables: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Validate that all required variables are defined.

        Use case: Check if all required variables are set before Terraform operations.
        """
        if not required_variables:
            required_variables = []

        existing_variables = await self.repository.list_by_project(
            project_name, workspace_name=workspace_name
        )
        existing_keys = {var.key for var in existing_variables}

        missing_variables = set(required_variables) - existing_keys
        extra_variables = (
            existing_keys - set(required_variables) if required_variables else set()
        )

        sensitive_count = sum(1 for var in existing_variables if var.is_sensitive)

        return {
            "total_variables": len(existing_variables),
            "required_variables": len(required_variables),
            "missing_variables": list(missing_variables),
            "extra_variables": list(extra_variables),
            "sensitive_variables_count": sensitive_count,
            "validation_passed": len(missing_variables) == 0,
        }

    async def get_variable_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about variables across all projects and workspaces.

        Use case: Dashboard or monitoring information.
        """
        all_variables = await self.repository.list_all(limit=10000)  # Get all variables

        stats: Dict[str, Any] = {
            "total_variables": len(all_variables),
            "projects": len(set(var.project_name for var in all_variables)),
            "workspaces": len(
                set(var.workspace_name for var in all_variables if var.workspace_name)
            ),
            "sensitive_variables": sum(1 for var in all_variables if var.is_sensitive),
            "variable_types": {},
            "variables_by_project": {},
            "variables_by_workspace": {},
        }

        # Count by variable type
        for var in all_variables:
            var_type = var.variable_type
            stats["variable_types"][var_type] = (
                stats["variable_types"].get(var_type, 0) + 1
            )

        # Count by project
        for var in all_variables:
            project = var.project_name
            stats["variables_by_project"][project] = (
                stats["variables_by_project"].get(project, 0) + 1
            )

        # Count by workspace
        for var in all_variables:
            if var.workspace_name:
                workspace = f"{var.project_name}/{var.workspace_name}"
                stats["variables_by_workspace"][workspace] = (
                    stats["variables_by_workspace"].get(workspace, 0) + 1
                )

        return stats

    async def import_variables_from_shell_script(
        self,
        shell_content: str,
        project_name: str,
        variable_type: VariableType,
        workspace_name: Optional[str] = None,
        comment_description: Optional[str] = None,
        overwrite_existing: bool = False,
    ) -> Dict[str, Any]:
        """Import variables from shell script content with export statements."""
        self._validate_import_requirements(variable_type, workspace_name)

        parsed_vars = self._parse_shell_content(shell_content, comment_description)
        result = await self._process_parsed_variables(
            parsed_vars, project_name, variable_type, workspace_name, overwrite_existing
        )

        logger.info(
            f"Shell import: {result['parsed_variables']} parsed, {result['created']} created, "
            f"{result['updated']} updated, {result['skipped']} skipped"
        )
        return result

    def _validate_import_requirements(
        self, variable_type: VariableType, workspace_name: Optional[str]
    ):
        """Validate import requirements."""
        if variable_type == VariableType.INSTANCE and not workspace_name:
            raise ValueError("workspace_name is required for INSTANCE variable type")

    def _parse_shell_content(
        self, content: str, default_comment: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Parse shell script content into structured variable data."""
        import re

        parsed_vars = []
        current_comment = default_comment or "Imported variables"

        for line_num, line in enumerate(content.split("\n"), 1):
            line = line.strip()

            if not line or line.startswith("#!"):
                continue

            if line.startswith("#"):
                comment_text = line[1:].strip()
                if comment_text and not comment_text.startswith("DO NOT EDIT"):
                    current_comment = comment_text
                continue

            # Parse export statements
            export_match = re.match(r"^export\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$", line)
            if export_match:
                key, value = export_match.groups()
                try:
                    parsed_vars.append(
                        {
                            "key": key,
                            "value": self._parse_shell_value(value),
                            "description": current_comment,
                            "is_sensitive": self._is_sensitive_variable(key),
                            "line_num": line_num,
                            "original_line": line,
                        }
                    )
                except Exception as e:
                    parsed_vars.append(
                        {
                            "error": f"Line {line_num}: Failed to parse '{line}' - {str(e)}"
                        }
                    )

        return parsed_vars

    async def _process_parsed_variables(
        self,
        parsed_vars: List[Dict[str, Any]],
        project_name: str,
        variable_type: VariableType,
        workspace_name: Optional[str],
        overwrite_existing: bool,
    ) -> Dict[str, Any]:
        """Process parsed variables and handle creation/updates."""
        stats = {
            "parsed_variables": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "created_variables": [],
            "updated_variables": [],
        }

        for var_data in parsed_vars:
            if "error" in var_data:
                stats["errors"].append(var_data["error"])  # type: ignore
                continue

            stats["parsed_variables"] += 1  # type: ignore

            try:
                variable_create = VariableCreate(
                    key=var_data["key"],
                    value=var_data["value"],
                    description=var_data["description"],
                    variable_type=variable_type,
                    is_sensitive=var_data["is_sensitive"],
                    project_name=project_name,
                    workspace_name=workspace_name,
                )

                existing_var = await self.repository.get_by_key_and_project(
                    var_data["key"], project_name, workspace_name
                )

                if existing_var:
                    if overwrite_existing:
                        await self._update_existing_variable(
                            existing_var, variable_create, stats
                        )
                    else:
                        stats["skipped"] += 1  # type: ignore
                else:
                    await self._create_new_variable(variable_create, stats)

            except Exception as e:
                stats["errors"].append(f"Line {var_data['line_num']}: {str(e)}")  # type: ignore

        return stats

    async def _update_existing_variable(
        self, existing_var: Variable, variable_data: VariableCreate, stats: Dict
    ):
        """Update an existing variable."""
        update_data = VariableUpdate(
            key=variable_data.key,
            project_name=variable_data.project_name,
            workspace_name=variable_data.workspace_name,
            value=variable_data.value,
            description=variable_data.description,
            variable_type=variable_data.variable_type,
            is_sensitive=variable_data.is_sensitive,
        )
        updated_var = await self.update_variable(existing_var.id, update_data)
        if updated_var:
            stats["updated_variables"].append(
                VariableResponse.model_validate(updated_var)
            )
            stats["updated"] += 1

    async def _create_new_variable(self, variable_data: VariableCreate, stats: Dict):
        """Create a new variable."""
        new_var = await self.create_variable(variable_data)
        stats["created_variables"].append(new_var)
        stats["created"] += 1

    def _parse_shell_value(self, value: str) -> Any:
        """Parse shell variable value, handling quotes and basic types."""
        value = value.strip()

        # Remove inline comments
        if " #" in value:
            value = value.split(" #")[0].strip()

        # Handle quoted strings
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]  # Remove quotes
        elif value.startswith("'") and value.endswith("'"):
            return value[1:-1]  # Remove quotes

        # Try to parse as number
        try:
            if "." in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            pass

        # Parse boolean
        if value.lower() in ("true", "false"):
            return value.lower() == "true"

        # Return as string if no special handling
        return value

    def _is_sensitive_variable(self, key: str) -> bool:
        """Determine if a variable should be marked as sensitive based on its key."""
        sensitive_keywords = [
            "password",
            "secret",
            "key",
            "token",
            "credential",
            "auth",
            "private",
            "webhook",
            "api_key",
        ]
        key_lower = key.lower()
        return any(keyword in key_lower for keyword in sensitive_keywords)
