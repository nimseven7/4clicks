import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.models import Inventory, IPAddress
from app.logger import logger
from app.repositories.inventory_repository import (
    InventoryRepository,
    IPAddressRepository,
)
from app.schemas.inventory_schema import (
    InventoryCreate,
    InventoryResponse,
    IPAddressResponse,
    TerraformSyncResponse,
)


class InventoryService:
    """Service for managing inventory operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.inventory_repo = InventoryRepository(db)
        self.ip_repo = IPAddressRepository(db)

    async def sync_from_terraform_outputs(
        self, project_name: str, workspace_name: Optional[str] = None
    ) -> TerraformSyncResponse:
        """
        Sync inventory from Terraform outputs by looking for outputs with '4clicks' = true.
        """  # noqa: E501
        try:
            outputs = await self._prepare_terraform_sync(project_name, workspace_name)
            sync_stats = await self._process_all_outputs(
                outputs, project_name, workspace_name
            )
            await self.db.commit()
            return self._create_sync_response(project_name, workspace_name, sync_stats)
        except (RuntimeError, json.JSONDecodeError):
            raise
        except Exception as e:
            logger.error(f"Error updating inventory from Terraform outputs: {e}")
            await self.db.rollback()
            raise

    async def _prepare_terraform_sync(
        self, project_name: str, workspace_name: Optional[str]
    ) -> Dict[str, Any]:
        """Prepare Terraform environment and get outputs."""
        terraform_dir = self._get_terraform_directory(project_name)
        await self._switch_terraform_workspace(terraform_dir, workspace_name)
        return await self._get_terraform_outputs(terraform_dir)

    async def _process_all_outputs(
        self, outputs: Dict[str, Any], project_name: str, workspace_name: Optional[str]
    ) -> Dict[str, Any]:
        """Process all Terraform outputs and return sync statistics."""
        sync_stats = self._initialize_sync_stats()

        for output_key, output_data in outputs.items():
            await self._process_terraform_output(
                output_key, output_data, project_name, workspace_name, sync_stats
            )

        return sync_stats

    def _get_terraform_directory(self, project_name: str) -> Path:
        """Get and validate the Terraform directory path."""
        terraform_dir = Path(f"infra/{project_name}/infra/terraform")
        if not terraform_dir.exists():
            raise FileNotFoundError(f"Terraform directory not found: {terraform_dir}")
        return terraform_dir

    async def _switch_terraform_workspace(
        self, terraform_dir: Path, workspace_name: Optional[str]
    ) -> None:
        """Switch to the specified Terraform workspace if provided."""
        if not workspace_name:
            return

        workspace_process = await asyncio.create_subprocess_exec(
            "terraform",
            "workspace",
            "select",
            workspace_name,
            cwd=terraform_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, workspace_stderr = await workspace_process.communicate()

        if workspace_process.returncode != 0:
            logger.warning(
                f"Could not switch to workspace {workspace_name}: {workspace_stderr.decode()}"
            )

    async def _get_terraform_outputs(self, terraform_dir: Path) -> Dict[str, Any]:
        """Execute terraform output and return parsed JSON."""
        process = await asyncio.create_subprocess_exec(
            "terraform",
            "output",
            "-json",
            cwd=terraform_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"Terraform command failed: {stderr.decode()}")

        return cast(Dict[str, Any], json.loads(stdout.decode()))

    def _initialize_sync_stats(self) -> Dict[str, Any]:
        """Initialize statistics tracking for sync operation."""
        return {
            "items_processed": 0,
            "items_created": 0,
            "items_updated": 0,
            "ips_created": 0,
            "ips_updated": 0,
            "created_inventories": [],
            "updated_inventories": [],
            "errors": [],
        }

    async def _process_terraform_output(
        self,
        output_key: str,
        output_data: Dict[str, Any],
        project_name: str,
        workspace_name: Optional[str],
        sync_stats: Dict[str, Any],
    ) -> None:
        """Process a single Terraform output and update sync statistics."""
        try:
            output_value = output_data.get("value", {})

            if not self._is_4clicks_inventory_output(output_value):
                return

            target_workspace = None if "global" in output_value else workspace_name
            result = await self._process_4clicks_output(
                project_name, target_workspace, output_key, output_value
            )

            self._update_sync_stats(sync_stats, result)

        except Exception as e:
            error_msg = f"Error processing output {output_key}: {str(e)}"
            logger.error(error_msg)
            sync_stats["errors"].append(error_msg)

    def _is_4clicks_inventory_output(self, output_value: Any) -> bool:
        """Check if output value is a valid 4clicks inventory output."""
        return (
            isinstance(output_value, dict)
            and output_value.get("4clicks") is True
            and output_value.get("type") == "inventory"
        )

    def _update_sync_stats(
        self, sync_stats: Dict[str, Any], result: Dict[str, Any]
    ) -> None:
        """Update sync statistics with results from processing an output."""
        sync_stats["items_processed"] += 1
        sync_stats["items_created"] += result["items_created"]
        sync_stats["items_updated"] += result["items_updated"]
        sync_stats["ips_created"] += result["ips_created"]
        sync_stats["ips_updated"] += result["ips_updated"]
        sync_stats["created_inventories"].extend(result["created_inventories"])
        sync_stats["updated_inventories"].extend(result["updated_inventories"])

    def _create_sync_response(
        self,
        project_name: str,
        workspace_name: Optional[str],
        sync_stats: Dict[str, Any],
    ) -> TerraformSyncResponse:
        """Create the final sync response from collected statistics."""
        return TerraformSyncResponse(
            project_name=project_name,
            workspace_name=workspace_name,
            items_processed=sync_stats["items_processed"],
            items_created=sync_stats["items_created"],
            items_updated=sync_stats["items_updated"],
            ips_created=sync_stats["ips_created"],
            ips_updated=sync_stats["ips_updated"],
            created_inventories=sync_stats["created_inventories"],
            updated_inventories=sync_stats["updated_inventories"],
            errors=sync_stats["errors"],
        )

    async def _process_4clicks_output(
        self,
        project_name: str,
        workspace_name: Optional[str],
        output_key: str,
        output_value: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process a single 4clicks output and create/update inventory items."""
        processing_stats = self._initialize_processing_stats()
        pending_associations: List[Any] = []

        inventory_names = self._extract_inventory_names(output_key, output_value)
        ips = self._extract_ips(output_key, output_value)

        if not ips:
            return processing_stats

        # Process each inventory name
        for inventory_name in inventory_names:
            current_inventory = await self._get_or_create_inventory(
                inventory_name,
                project_name,
                workspace_name,
                output_key,
                output_value,
                processing_stats,
            )

            # Process IPs and collect associations
            await self._process_ips_for_inventory(
                ips,
                output_key,
                workspace_name,
                current_inventory,
                inventory_name,
                processing_stats,
                pending_associations,
            )

        # Process all associations at the end after all objects are created
        await self._process_pending_associations(pending_associations)

        return processing_stats

    def _initialize_processing_stats(self) -> Dict[str, Any]:
        """Initialize statistics for processing a single output."""
        return {
            "items_created": 0,
            "items_updated": 0,
            "ips_created": 0,
            "ips_updated": 0,
            "created_inventories": [],
            "updated_inventories": [],
        }

    def _extract_inventory_names(
        self, output_key: str, output_value: Dict[str, Any]
    ) -> List[str]:
        """Extract and normalize inventory names from output value."""
        inventory_names_raw = output_value.get("inventory_names", [])
        if isinstance(inventory_names_raw, str):
            inventory_names = [inventory_names_raw]
        else:
            inventory_names = list(inventory_names_raw) if inventory_names_raw else []

        if not inventory_names:
            inventory_names = [output_key]
            logger.info(
                f"No inventory_names found in output {output_key}, using output key as inventory name"
            )

        return inventory_names

    def _extract_ips(self, output_key: str, output_value: Dict[str, Any]) -> List[str]:
        """Extract and normalize IP addresses from output value."""
        ips_raw = output_value.get("ips", [])
        if isinstance(ips_raw, str):
            ips = [ips_raw]
        else:
            ips = list(ips_raw) if ips_raw else []

        if not ips:
            logger.warning(f"No ips found in output {output_key}")

        return ips

    async def _get_or_create_inventory(
        self,
        inventory_name: str,
        project_name: str,
        workspace_name: Optional[str],
        output_key: str,
        output_value: Dict[str, Any],
        processing_stats: Dict[str, Any],
    ) -> Inventory:
        """Get existing inventory or create new one, handling constraint checks."""
        # Check for existing inventory with unique constraint (name + project only)
        existing_constraint = await self.inventory_repo.get_by_name_and_project_only(
            inventory_name, project_name
        )

        if existing_constraint:
            logger.info(
                f"Inventory {inventory_name} already exists for project {project_name}, only updating IPs"
            )
            processing_stats["items_updated"] += 1
            processing_stats["updated_inventories"].append(inventory_name)
            return existing_constraint

        # Check for exact match (name + project + workspace)
        existing_exact = await self.inventory_repo.get_by_name_and_project(
            inventory_name, project_name, workspace_name
        )

        inventory_data = self._build_inventory_data(
            inventory_name, project_name, workspace_name, output_key, output_value
        )

        if existing_exact:
            await self.inventory_repo.update(existing_exact.id, **inventory_data)
            processing_stats["items_updated"] += 1
            processing_stats["updated_inventories"].append(inventory_name)
            logger.info(f"Updated inventory: {inventory_name}")
            return existing_exact
        else:
            new_inventory = await self.inventory_repo.create(**inventory_data)
            processing_stats["items_created"] += 1
            processing_stats["created_inventories"].append(inventory_name)
            logger.info(f"Created inventory: {inventory_name}")
            return new_inventory

    def _build_inventory_data(
        self,
        inventory_name: str,
        project_name: str,
        workspace_name: Optional[str],
        output_key: str,
        output_value: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build inventory data dictionary for create/update operations."""
        return {
            "name": inventory_name,
            "project_name": project_name,
            "workspace_name": workspace_name,
            "description": output_value.get(
                "description",
                f"Auto-generated from Terraform output: {output_key}",
            ),
            "metadata_": {
                "terraform_output_key": output_key,
                "terraform_workspace": output_value.get("workspace"),
                "deployment_date": output_value.get("deployment_date"),
                "type": output_value.get("type"),
                "urls": output_value.get("urls", []),
            },
        }

    async def _process_ips_for_inventory(
        self,
        ips: List[str],
        output_key: str,
        workspace_name: Optional[str],
        current_inventory: Inventory,
        inventory_name: str,
        processing_stats: Dict[str, Any],
        pending_associations: List[Dict[str, Any]],
    ) -> None:
        """Process IP addresses for a specific inventory."""
        for ip in ips:
            ip_str = str(ip)
            current_ip = await self._get_or_create_ip(
                ip_str, output_key, workspace_name, processing_stats
            )

            pending_associations.append(
                {
                    "inventory": current_inventory,
                    "ip": current_ip,
                    "inventory_name": inventory_name,
                    "ip_str": ip_str,
                }
            )

    async def _get_or_create_ip(
        self,
        ip_str: str,
        output_key: str,
        workspace_name: Optional[str],
        processing_stats: Dict[str, Any],
    ) -> IPAddress:
        """Get existing IP or create new one."""
        existing_ip = await self.ip_repo.get_by_ip(ip_str)
        if existing_ip:
            processing_stats["ips_updated"] += 1
            return existing_ip
        else:
            new_ip = await self.ip_repo.create(
                ip=ip_str,
                description=f"IP from Terraform output: {output_key}",
                workspace=workspace_name,
            )
            processing_stats["ips_created"] += 1
            logger.info(f"Created IP: {ip_str}")
            return new_ip

    async def _process_pending_associations(
        self, pending_associations: List[Dict[str, Any]]
    ) -> None:
        """Process all pending IP-inventory associations."""
        for assoc in pending_associations:
            await self._ensure_ip_inventory_association(
                assoc["inventory"],
                assoc["ip"],
                assoc["inventory_name"],
                assoc["ip_str"],
            )

    async def _ensure_ip_inventory_association(
        self,
        inventory: Inventory,
        ip_address: IPAddress,
        inventory_name: str,
        ip_str: str,
    ):
        """
        Ensure IP address is associated with inventory using explicit SQL operations.
        This avoids the greenlet issues with SQLAlchemy relationship manipulation.
        """
        from sqlalchemy import text

        # We need to flush to get IDs for the association, but we'll do it safely
        try:
            # Check if we have IDs, if not, we need to flush first
            if inventory.id is None:
                await self.db.flush()
            if ip_address.id is None:
                await self.db.flush()

            # Check if association already exists
            check_query = text(
                """
                SELECT COUNT(*) FROM inventory_ip_association 
                WHERE inventory_id = :inventory_id AND ip_address_id = :ip_address_id
            """
            )

            result = await self.db.execute(
                check_query,
                {"inventory_id": inventory.id, "ip_address_id": ip_address.id},
            )

            count = result.scalar()

            if count == 0:
                # Create the association
                insert_query = text(
                    """
                    INSERT INTO inventory_ip_association (inventory_id, ip_address_id)
                    VALUES (:inventory_id, :ip_address_id)
                """
                )

                await self.db.execute(
                    insert_query,
                    {"inventory_id": inventory.id, "ip_address_id": ip_address.id},
                )

                logger.info(f"Associated IP {ip_str} with inventory {inventory_name}")
            else:
                logger.debug(
                    f"IP {ip_str} already associated with inventory {inventory_name}"
                )

        except Exception as e:
            logger.error(f"Error creating IP-inventory association: {e}")
            # Fallback: try the traditional SQLAlchemy way if raw SQL fails
            try:
                # Refresh objects to ensure they have proper state
                await self.db.refresh(inventory)
                await self.db.refresh(ip_address)

                # Check if already associated by IP string comparison
                existing_ips = [ip.ip for ip in inventory.ip_addresses]
                if ip_str not in existing_ips:
                    inventory.ip_addresses.append(ip_address)
                    logger.info(
                        f"Associated IP {ip_str} with inventory {inventory_name} (fallback method)"  # noqa: E501
                    )
            except Exception as fallback_error:
                logger.error(
                    f"Fallback association method also failed: {fallback_error}"
                )
                # Continue processing other IPs even if this one fails
                pass

    async def _find_orphaned_workspace_ips(
        self, workspace_name: str
    ) -> List[IPAddress]:
        """
        Find IP addresses that belong to a workspace but are no longer associated with any inventory.
        """
        from sqlalchemy import text

        # Find IPs that belong to this workspace but have no inventory associations
        query = text(
            """
            SELECT ip.* FROM ip_addresses ip 
            WHERE ip.workspace = :workspace_name 
            AND NOT EXISTS (
                SELECT 1 FROM inventory_ip_association assoc 
                WHERE assoc.ip_address_id = ip.id
            )
        """
        )

        result = await self.db.execute(query, {"workspace_name": workspace_name})
        ip_rows = result.fetchall()

        # Convert rows to IPAddress objects
        orphaned_ips = []
        for row in ip_rows:
            ip = IPAddress(
                id=row.id,
                ip=row.ip,
                description=row.description,
                deployment_date=row.deployment_date,
                workspace=row.workspace,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            orphaned_ips.append(ip)

        return orphaned_ips

    async def cleanup_workspace_inventory(
        self, project_name: str, workspace_name: Optional[str] = None
    ) -> int:
        """
        Clean up all inventory items for a workspace.

        Use case: Remove all inventory items when a workspace is destroyed.
        Also removes workspace-specific IP addresses that are no longer associated
        with any inventory.
        Returns the number of items deleted.
        """
        try:
            inventories = await self.inventory_repo.get_by_project_workspace(
                project_name, workspace_name
            )

            deleted_count = 0
            for inventory in inventories:
                # Delete the inventory item (cascade will handle IP associations)
                success = await self.inventory_repo.delete(inventory.id)
                if success:
                    deleted_count += 1
                    logger.info(
                        f"Deleted inventory '{inventory.name}' (ID: {inventory.id})"
                    )

            # Clean up orphaned IP addresses that belong to this workspace
            if workspace_name:
                orphaned_ips = await self._find_orphaned_workspace_ips(workspace_name)
                deleted_ip_count = 0
                for ip in orphaned_ips:
                    success = await self.ip_repo.delete(ip.id)
                    if success:
                        deleted_ip_count += 1
                        logger.info(f"Deleted orphaned IP '{ip.ip}' (ID: {ip.id})")

                if deleted_ip_count > 0:
                    logger.info(f"Cleaned up {deleted_ip_count} orphaned IP addresses")

            await self.db.commit()

            logger.info(
                f"Cleaned up {deleted_count} inventory items for project '{project_name}'"  # noqa: E501
                f"{f' workspace {workspace_name}' if workspace_name else ''}"
            )

            return deleted_count

        except Exception as e:
            logger.error(
                f"Error cleaning up inventory for {project_name}/{workspace_name}: {e}"
            )
            await self.db.rollback()
            raise

    async def get_inventory(
        self, project_name: str, workspace_name: Optional[str] = None
    ) -> List[InventoryResponse]:
        """Get inventory for a specific project and optional workspace."""
        inventories = await self.inventory_repo.get_by_project_workspace(
            project_name, workspace_name
        )
        return [
            InventoryResponse(
                id=inv.id,
                name=inv.name,
                project_name=inv.project_name,
                workspace_name=inv.workspace_name,
                description=inv.description,
                metadata=inv.metadata_,
                deployment_date=inv.deployment_date,
                created_at=inv.created_at,
                updated_at=inv.updated_at,
                ip_addresses=[
                    IPAddressResponse(
                        id=ip.id,
                        ip=ip.ip,
                        description=ip.description,
                        workspace=ip.workspace,
                        deployment_date=ip.deployment_date,
                        created_at=ip.created_at,
                        updated_at=ip.updated_at,
                    )
                    for ip in inv.ip_addresses
                ],
            )
            for inv in inventories
        ]
