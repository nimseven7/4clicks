"""Database models for the application."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.databases.database import Base


class TaskTemplateType(enum.Enum):
    """Enum for task template types."""

    ANSIBLE = "ansible"
    BASH = "bash"


class VariableType(enum.Enum):
    """Enum for variable types."""

    TERRAFORM = "terraform"  # Terraform variables
    PROJECT = "project"  # Project variables, shared across all instances
    INSTANCE = "instance"  # Instance variables, different for each project+workspace


class TaskStatus(enum.Enum):
    """Enum for task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SSHKeyType(enum.Enum):
    """Enum for SSH key types."""

    ED25519 = "ed25519"
    RSA = "rsa"


# Association table for many-to-many relationship between Inventory and IPAddress
inventory_ip_association = Table(
    "inventory_ip_association",
    Base.metadata,
    Column("inventory_id", Integer, ForeignKey("inventory.id", ondelete="CASCADE")),
    Column("ip_address_id", Integer, ForeignKey("ip_addresses.id", ondelete="CASCADE")),
)


class SSHKeyPair(Base):
    """Model for storing SSH key pairs for task authentication."""

    __tablename__ = "ssh_key_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Key metadata
    key_type: Mapped[SSHKeyType] = mapped_column(Enum(SSHKeyType), index=True)
    key_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # For RSA keys
    fingerprint: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Encrypted private key (base64 encoded)
    private_key_encrypted: Mapped[str] = mapped_column(Text)
    # Public key (plain text, safe to store)
    public_key: Mapped[str] = mapped_column(Text)

    # Project association
    project_name: Mapped[str] = mapped_column(String(255), index=True, nullable=True)

    # Key status and metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Optional passphrase hint (never store actual passphrase)
    passphrase_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationship with tasks
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="ssh_key")

    # Indexes for faster lookups
    __table_args__ = (
        Index("ix_ssh_key_name_project", "name", "project_name", unique=True),
        Index("ix_ssh_key_fingerprint", "fingerprint"),
        Index("ix_ssh_key_project_active", "project_name", "is_active"),
    )


class Variable(Base):
    """Model for Terraform variables.

    Variables are stored in the database and reference projects and workspaces
    by their string identifiers since projects are filesystem-based and
    workspaces are managed by Terraform itself.
    """

    __tablename__ = "variables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[Any] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    variable_type: Mapped[VariableType] = mapped_column(
        Enum(VariableType), default=VariableType.TERRAFORM, nullable=False
    )
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)

    # String references to projects and workspaces (not foreign keys)
    project_name: Mapped[str] = mapped_column(String(255), index=True)
    workspace_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )


class Inventory(Base):
    """Model for storing VM inventory information, generally from Terraform outputs."""

    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)  # Name of the inventory
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Optional description of the inventory

    project_name: Mapped[str] = mapped_column(String(255), index=True)
    workspace_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    deployment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # When the inventory was deployed

    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, name="metadata"
    )  # Optional metadata about the inventory

    # Many-to-many relationship with IPAddress
    ip_addresses: Mapped[list["IPAddress"]] = relationship(
        "IPAddress", secondary=inventory_ip_association, back_populates="inventories"
    )

    # Indexes for faster lookups
    __table_args__ = (
        Index("ix_inventory_project_workspace", "project_name", "workspace_name"),
        Index("ix_inventory_name_project", "name", "project_name", unique=True),
    )


class IPAddress(Base):
    """Model for storing IP address information."""

    __tablename__ = "ip_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ip: Mapped[str] = mapped_column(String(45), index=True)  # IPv4 or IPv6
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Optional description of the IP address
    deployment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # When the IP was deployed

    workspace: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Optional workspace name

    # Many-to-many relationship with Inventory
    inventories: Mapped[list[Inventory]] = relationship(
        "Inventory", secondary=inventory_ip_association, back_populates="ip_addresses"
    )


# Association table for many-to-many relationship between Task and IPAddress
task_ip_association = Table(
    "task_ip_association",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE")),
    Column("ip_address_id", Integer, ForeignKey("ip_addresses.id", ondelete="CASCADE")),
)

# Association table for many-to-many relationship between Task and Inventory
task_inventory_association = Table(
    "task_inventory_association",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE")),
    Column("inventory_id", Integer, ForeignKey("inventory.id", ondelete="CASCADE")),
)


class TaskTemplate(Base):
    """Model for storing reusable task templates (ansible playbook or bash script)."""

    __tablename__ = "task_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Task template type: 'ansible' or 'bash'
    template_type: Mapped[TaskTemplateType] = mapped_column(
        Enum(TaskTemplateType), index=True
    )

    # File path relative to tasks folder (e.g., "ansible/deploy.yml" or "scripts/backup.sh")
    file_path: Mapped[str] = mapped_column(String(500))

    # Project association
    project_name: Mapped[str] = mapped_column(String(255), index=True)

    # Optional parameters schema (JSON)
    parameters_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    # Whether the template is active
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationship with tasks
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="template")

    # Indexes for faster lookups
    __table_args__ = (
        Index("ix_task_template_name_project", "name", "project_name", unique=True),
        Index("ix_task_template_type", "template_type"),
    )


class Task(Base):
    """Model for storing task executions."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Task status: 'pending', 'running', 'completed', 'failed', 'cancelled'
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING, index=True
    )

    # Task parameters (JSON)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Execution logs
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Exit code from execution
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Execution timestamps
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Foreign key to task template
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("task_templates.id"))
    template: Mapped[TaskTemplate] = relationship(
        "TaskTemplate", back_populates="tasks"
    )

    # Optional SSH key for authentication
    ssh_key_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ssh_key_pairs.id"), nullable=True
    )
    ssh_key: Mapped["SSHKeyPair | None"] = relationship(
        "SSHKeyPair", back_populates="tasks"
    )

    # Project association
    project_name: Mapped[str] = mapped_column(String(255), index=True)
    workspace_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Many-to-many relationships with targets
    target_ip_addresses: Mapped[list[IPAddress]] = relationship(
        "IPAddress", secondary=task_ip_association
    )
    target_inventories: Mapped[list[Inventory]] = relationship(
        "Inventory", secondary=task_inventory_association
    )

    # Indexes for faster lookups
    __table_args__ = (
        Index("ix_task_status", "status"),
        Index("ix_task_project_workspace", "project_name", "workspace_name"),
        Index("ix_task_created_at", "created_at"),
    )
