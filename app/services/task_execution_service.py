"""Service layer for task execution with streaming support."""

import asyncio
import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, Template
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.databases.models import (
    Inventory,
    IPAddress,
    SSHKeyPair,
    Task,
    TaskStatus,
    TaskTemplate,
    TaskTemplateType,
)
from app.logger import logger
from app.repositories.inventory_repository import (
    InventoryRepository,
    IPAddressRepository,
)
from app.repositories.task_repository import (
    SSHKeyRepository,
    TaskRepository,
    TaskTemplateRepository,
)
from app.schemas.task_schema import TaskCreate, TaskResponse
from app.services.ssh_key_service import SSHKeyService

# Base tasks directory path
TASKS_DIR = Path(__file__).parent.parent.parent / "tasks"

# Common SSH options and timeouts
SSH_COMMON_ARGS = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=30 -o ServerAliveInterval=10 -o ServerAliveCountMax=3"  # noqa: E501
ANSIBLE_TIMEOUT = "60"
PROCESS_START_TIMEOUT = 10.0
OUTPUT_TIMEOUT = 30.0
OVERALL_TIMEOUT = 120.0


class TaskExecutionService:
    """Service for task execution operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.task_repo = TaskRepository(session)
        self.template_repo = TaskTemplateRepository(session)
        self.inventory_repo = InventoryRepository(session)
        self.ip_repo = IPAddressRepository(session)
        self.ssh_key_repo = SSHKeyRepository(session)
        self.ssh_key_service = SSHKeyService(self.ssh_key_repo, session)

    # SSH Key Management (consolidated)
    @staticmethod
    def _get_encryption_key() -> bytes:
        """Get encryption key for private key storage."""
        encryption_key = os.getenv("SSH_KEY_ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError("SSH_KEY_ENCRYPTION_KEY environment variable is required")
        return hashlib.sha256(encryption_key.encode()).digest()

    @staticmethod
    def _render_template_with_parameters(
        template_path: Path, parameters: Optional[Dict] = None
    ) -> str:
        """Render template file content with Jinja2 parameters."""
        if not parameters:
            parameters = {}

        try:
            # Read the template file
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            # Create Jinja2 template and render with parameters
            template = Template(template_content)
            rendered_content = template.render(**parameters)

            return rendered_content
        except Exception as e:
            raise Exception(f"Failed to render template {template_path}: {str(e)}")

    @staticmethod
    def _decrypt_private_key(encrypted_key: str) -> str:
        """Decrypt private key from storage."""
        try:
            encrypted_data = base64.b64decode(encrypted_key.encode("utf-8"))
            iv = encrypted_data[:16]
            encrypted_content = encrypted_data[16:]
            key = TaskExecutionService._get_encryption_key()

            cipher = Cipher(
                algorithms.AES(key), modes.CBC(iv), backend=default_backend()
            )
            decryptor = cipher.decryptor()
            padded_key = decryptor.update(encrypted_content) + decryptor.finalize()

            padding_length = padded_key[-1]
            return padded_key[:-padding_length].decode("utf-8")
        except Exception as e:
            raise Exception(f"Failed to decrypt private key: {str(e)}")

    @staticmethod
    def _write_ssh_key_to_temp_file(ssh_key_data: Dict) -> str:
        """Write SSH key to a temporary file."""
        decrypted_key = TaskExecutionService._decrypt_private_key(
            ssh_key_data["private_key_encrypted"]
        )

        temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pem")
        temp_file.write(decrypted_key)
        temp_file.close()
        os.chmod(temp_file.name, 0o600)
        return temp_file.name

    @staticmethod
    def _cleanup_ssh_key(key_file_path: Optional[str]) -> None:
        """Clean up temporary SSH key file."""
        if key_file_path and os.path.exists(key_file_path):
            try:
                os.unlink(key_file_path)
            except OSError:
                pass

    # Command Execution (consolidated)
    @staticmethod
    async def _stream_command_output(
        cmd: List[str], stdin_file: Optional[Path] = None
    ) -> AsyncGenerator[str, None]:
        """Stream command output with proper error handling."""
        try:
            stdin_data = None
            if stdin_file and stdin_file.exists():
                stdin_data = stdin_file.read_bytes()

            # Start process with timeout
            try:
                process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *cmd,
                        stdin=asyncio.subprocess.PIPE if stdin_data else None,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                    ),
                    timeout=PROCESS_START_TIMEOUT,
                )
            except asyncio.TimeoutError:
                yield f'data: {{"status": "error", "message": "❌ Command failed to start within {PROCESS_START_TIMEOUT} seconds"}}\n\n'  # noqa: E501
                return

            if stdin_data and process.stdin:
                process.stdin.write(stdin_data)
                process.stdin.close()

            # Stream output with timeout
            try:
                if process.stdout:
                    while True:
                        try:
                            line = await asyncio.wait_for(
                                process.stdout.readline(), timeout=OUTPUT_TIMEOUT
                            )
                            if not line:
                                break

                            clean_line = line.decode("utf-8", errors="ignore").rstrip(
                                "\n\r"
                            )
                            if clean_line:
                                escaped_line = clean_line.replace('"', '\\"').replace(
                                    "\n", "\\n"
                                )
                                yield f'data: {{"status": "output", "message": "{escaped_line}"}}\n\n'

                        except asyncio.TimeoutError:
                            if process.returncode is None:
                                yield f'data: {{"status": "warning", "message": "⚠️ No output for {OUTPUT_TIMEOUT} seconds, command may be hanging..."}}\n\n'  # noqa: E501
                                continue
                            else:
                                break

                # Wait for completion with timeout
                try:
                    await asyncio.wait_for(process.wait(), timeout=OVERALL_TIMEOUT)
                except asyncio.TimeoutError:
                    yield f'data: {{"status": "error", "message": "❌ Command timed out after {OVERALL_TIMEOUT/60} minutes, terminating..."}}\n\n'  # noqa: E501
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        process.kill()
                    return

            except asyncio.TimeoutError:
                yield f'data: {{"status": "error", "message": "❌ Command execution timed out"}}\n\n'
                process.terminate()
                return

            if process.returncode != 0:
                yield f'data: {{"status": "error", "message": "❌ Command failed with exit code {process.returncode}"}}\n\n'  # noqa: E501
            else:
                yield f'data: {{"status": "success", "message": "✅ Command completed successfully"}}\n\n'

        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            yield f'data: {{"status": "error", "message": "❌ Failed to execute command: {str(e)}"}}\n\n'

    # Target Host Resolution (consolidated)
    async def _get_target_hosts(self, task_data: TaskCreate) -> List[str]:
        """Get target hosts from task data."""
        target_hosts = []

        # Add individual IP addresses
        if task_data.target_ip_addresses:
            for ip_id in task_data.target_ip_addresses:
                ip_address = await self.ip_repo.get_by_id(ip_id)
                if ip_address:
                    target_hosts.append(ip_address.ip)

        # Add inventory hosts
        if task_data.target_inventories:
            for inventory_id in task_data.target_inventories:
                inventory = await self.inventory_repo.get_by_id(inventory_id)
                if inventory and inventory.ip_addresses:
                    for ip_addr in inventory.ip_addresses:
                        if ip_addr.ip not in target_hosts:
                            target_hosts.append(ip_addr.ip)

        return target_hosts if target_hosts else ["localhost"]

    # Task Association Handling
    async def _handle_target_associations(
        self, task: Task, task_data: TaskCreate
    ) -> None:
        """Handle target IP addresses and inventory associations for a task."""
        # Handle target IP addresses
        if task_data.target_ip_addresses:
            for ip_id in task_data.target_ip_addresses:
                ip_address = await self.ip_repo.get_by_id(ip_id)
                if ip_address:
                    await self.session.execute(
                        text(
                            "INSERT INTO task_ip_association (task_id, ip_address_id) VALUES (:task_id, :ip_id)"
                        ),
                        {"task_id": task.id, "ip_id": ip_address.id},
                    )

        # Handle target inventories
        if task_data.target_inventories:
            for inventory_id in task_data.target_inventories:
                inventory = await self.inventory_repo.get_by_id(inventory_id)
                if inventory:
                    await self.session.execute(
                        text(
                            "INSERT INTO task_inventory_association (task_id, inventory_id) VALUES (:task_id, :inventory_id)"  # noqa: E501
                        ),
                        {"task_id": task.id, "inventory_id": inventory.id},
                    )

    # Ansible Task Execution (consolidated)
    async def _execute_ansible_task(
        self,
        task: Task,
        template: TaskTemplate,
        target_hosts: List[str],
        ssh_key_path: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Execute Ansible task with streaming output."""
        async for chunk in self._execute_ansible_task_static(
            task, template, target_hosts, ssh_key_path
        ):
            yield chunk

    @staticmethod
    async def _execute_ansible_task_static(
        task: Task,
        template: TaskTemplate,
        target_hosts: List[str],
        ssh_key_path: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Execute Ansible task with streaming output (static version)."""
        yield 'data: {"status": "ansible_prep", "message": "🔧 Preparing Ansible execution..."}\n\n'

        # Create inventory file
        inventory_content = "[targets]\n" + "\n".join(target_hosts)
        inventory_file = tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".ini"
        )
        inventory_file.write(inventory_content)
        inventory_file.close()

        try:
            # Build ansible-playbook command
            playbook_path = TASKS_DIR / template.file_path
            cmd = [
                "uv",
                "run",
                "ansible-playbook",
                "-i",
                inventory_file.name,
                str(playbook_path),
                "-v",
                "--ssh-common-args",
                SSH_COMMON_ARGS,
                "--timeout",
                ANSIBLE_TIMEOUT,
            ]

            if ssh_key_path:
                cmd.extend(["--private-key", ssh_key_path])

            if task.parameters:
                for key, value in task.parameters.items():
                    cmd.extend(["-e", f"{key}={value}"])

            yield f'data: {{"status": "executing", "message": "▶️ Running: {" ".join(cmd)}"}}\n\n'

            async for output_chunk in TaskExecutionService._stream_command_output(cmd):
                yield output_chunk

        finally:
            if os.path.exists(inventory_file.name):
                os.unlink(inventory_file.name)

    # Bash Task Execution (consolidated)
    async def _execute_bash_task(
        self,
        task: Task,
        template: TaskTemplate,
        target_hosts: List[str],
        ssh_key_path: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Execute Bash task with streaming output."""
        async for chunk in self._execute_bash_task_static(
            task, template, target_hosts, ssh_key_path
        ):
            yield chunk

    @staticmethod
    async def _execute_bash_task_static(
        task: Task,
        template: TaskTemplate,
        target_hosts: List[str],
        ssh_key_path: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Execute Bash task with streaming output (static version)."""
        yield 'data: {"status": "bash_prep", "message": "🐚 Preparing Bash execution..."}\n\n'

        script_path = TASKS_DIR / template.file_path

        # Render template with parameters
        try:
            rendered_script_content = (
                TaskExecutionService._render_template_with_parameters(
                    script_path, task.parameters
                )
            )
            yield 'data: {"status": "bash_prep", "message": "🔧 Template rendered with parameters..."}\n\n'
        except Exception as e:
            yield f'data: {{"status": "error", "message": "❌ Template rendering failed: {str(e)}"}}\n\n'
            return

        # Create temporary file with rendered content
        temp_script = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".sh")
        temp_script.write(rendered_script_content)
        temp_script.close()
        os.chmod(temp_script.name, 0o755)

        try:
            for host in target_hosts:
                yield f'data: {{"status": "executing", "message": "🔄 Executing on {host}..."}}\n\n'

                if host == "localhost":
                    cmd = ["bash", temp_script.name]
                    # For local execution, we'll use the stream_command_output method
                    async for (
                        output_chunk
                    ) in TaskExecutionService._stream_command_output(cmd):
                        yield output_chunk
                else:
                    # Remote execution via SSH
                    cmd = ["ssh"]
                    if ssh_key_path:
                        cmd.extend(["-i", ssh_key_path])
                    cmd.extend(
                        [
                            "-o",
                            "StrictHostKeyChecking=no",
                            "-o",
                            "UserKnownHostsFile=/dev/null",
                            host,
                            "bash -s",
                        ]
                    )

                    yield f'data: {{"status": "executing", "message": "▶️ Running SSH: {host}"}}\n\n'

                    async for (
                        output_chunk
                    ) in TaskExecutionService._stream_command_output(
                        cmd, stdin_file=Path(temp_script.name)
                    ):
                        yield output_chunk
        finally:
            # Clean up temporary script file
            if os.path.exists(temp_script.name):
                os.unlink(temp_script.name)

    # Main execution methods
    async def prepare_task_execution(self, task_data: TaskCreate) -> Dict:
        """Prepare task execution by handling all database operations."""
        task = None
        try:
            # Validate template exists
            template = await self.template_repo.get_by_id(task_data.template_id)
            if not template:
                raise HTTPException(status_code=404, detail="Task template not found")

            # Create the task
            task = await self.task_repo.create_from_task_schema(
                task_data, task_data.template_id
            )
            await self.session.flush()
            await self.session.refresh(task)

            # Handle target associations
            await self._handle_target_associations(task, task_data)
            await self.session.commit()
            await self.session.refresh(task)

            # Update task status to running
            await self.task_repo.update_status(task.id, TaskStatus.RUNNING.name)
            await self.session.commit()

            # Resolve target hosts
            target_hosts = await self._get_target_hosts(task_data)

            # Get SSH key data if needed
            ssh_key_data = None
            if task_data.ssh_key_id is not None:
                ssh_key = await self.ssh_key_repo.get_by_id(task_data.ssh_key_id)
                if ssh_key:
                    ssh_key_data = {
                        "private_key_encrypted": ssh_key.private_key_encrypted,
                        "public_key": ssh_key.public_key,
                        "name": ssh_key.name,
                    }

            return {
                "task": task,
                "template": template,
                "target_hosts": target_hosts,
                "ssh_key_data": ssh_key_data,
                "task_data": task_data,
            }

        except Exception as e:
            if self.session:
                await self.session.rollback()

            # Clean up task if it was created
            if task and hasattr(task, "id"):
                try:
                    await self.task_repo.update_status(task.id, TaskStatus.FAILED.name)
                    await self.session.commit()
                except Exception:
                    pass

            raise e

    @staticmethod
    async def execute_task_streaming_static(
        task_execution_data: Dict,
    ) -> AsyncGenerator[str, None]:
        """Static method to execute a task with streaming output (no database operations)."""
        task = task_execution_data["task"]
        template = task_execution_data["template"]
        target_hosts = task_execution_data["target_hosts"]
        ssh_key_data = task_execution_data["ssh_key_data"]

        try:
            yield 'data: {"status": "preparing", "message": "📋 Preparing task execution..."}\n\n'

            # Prepare SSH key if needed
            ssh_key_path = None
            if ssh_key_data:
                ssh_key_path = TaskExecutionService._write_ssh_key_to_temp_file(
                    ssh_key_data
                )

            # Execute based on template type
            if template.template_type == TaskTemplateType.ANSIBLE:
                async for (
                    log_chunk
                ) in TaskExecutionService._execute_ansible_task_static(
                    task, template, target_hosts, ssh_key_path
                ):
                    yield log_chunk
            elif template.template_type == TaskTemplateType.BASH:
                async for log_chunk in TaskExecutionService._execute_bash_task_static(
                    task, template, target_hosts, ssh_key_path
                ):
                    yield log_chunk
            else:
                error_msg = f"❌ Unsupported template type: {template.template_type}"
                yield f'data: {{"status": "error", "message": "{error_msg}"}}\n\n'
                return

            yield 'data: {"status": "completed", "message": "✅ Task execution completed"}\n\n'

        except Exception as e:
            error_msg = f"❌ Execution failed: {str(e)}"
            yield f'data: {{"status": "error", "message": "{error_msg}"}}\n\n'

        finally:
            TaskExecutionService._cleanup_ssh_key(ssh_key_path)

    # Simple API methods
    async def get_task(self, task_id: int) -> TaskResponse:
        """Get a task by ID."""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskResponse.model_validate(task)

    async def list_tasks_by_project(
        self,
        project_name: str,
        workspace_name: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[TaskResponse]:
        """List tasks for a project and optional workspace."""
        tasks = await self.task_repo.list_by_project(
            project_name, workspace_name=workspace_name, skip=skip, limit=limit
        )
        return [TaskResponse.model_validate(task) for task in tasks]

    async def mark_task_as_completed(self, task_execution_data: Dict) -> None:
        """Mark a task as completed."""
        task = task_execution_data["task"]
        await self.task_repo.update_status(task.id, TaskStatus.COMPLETED.name)
        await self.session.commit()
