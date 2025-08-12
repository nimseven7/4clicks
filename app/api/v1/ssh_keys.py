from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_handlers import handle_service_exceptions
from app.databases.database import get_db_session
from app.repositories.task_repository import SSHKeyRepository
from app.schemas.task_schema import (
    SSHKeyPairGenerate,
    SSHKeyPairImport,
    SSHKeyPairListResponse,
    SSHKeyPairResponse,
    SSHKeyPairUpdate,
    SSHPublicKeyResponse,
)
from app.services.ssh_key_service import SSHKeyService

# SSH Key Management Endpoints

router = APIRouter(
    prefix="/ssh-keys",
    tags=["SSH Key Management"],
)


@router.post("/generate", response_model=SSHKeyPairResponse, status_code=201)
@handle_service_exceptions
async def generate_ssh_key(
    key_data: SSHKeyPairGenerate, db: AsyncSession = Depends(get_db_session)
):
    """
    Generate a new SSH key pair.

    Supports ED25519 (recommended) and RSA key types.
    Keys are encrypted and stored securely.
    """
    ssh_key_repository = SSHKeyRepository(db)
    service = SSHKeyService(ssh_key_repository, db)
    return await service.generate_key_pair(key_data)


@router.post("/import", response_model=SSHKeyPairResponse, status_code=201)
@handle_service_exceptions
async def import_ssh_key(
    key_data: SSHKeyPairImport, db: AsyncSession = Depends(get_db_session)
):
    """
    Import an existing SSH key pair.

    Validates the private key and derives the public key if not provided.
    """
    ssh_key_repository = SSHKeyRepository(db)
    service = SSHKeyService(ssh_key_repository, db)
    return await service.import_key_pair(key_data)


@router.get("", response_model=SSHKeyPairListResponse)
@handle_service_exceptions
async def list_ssh_keys(
    project_name: Optional[str] = Query(None, description="Project name"),
    skip: int = Query(0, ge=0, description="Number of keys to skip"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of keys to return"
    ),
    active_only: bool = Query(True, description="Only return active keys"),
    db: AsyncSession = Depends(get_db_session),
):
    """List SSH keys for a project."""
    ssh_key_repository = SSHKeyRepository(db)
    service = SSHKeyService(ssh_key_repository, db)
    ssh_keys = await service.list_keys_by_project(
        project_name, skip=skip, limit=limit, active_only=active_only
    )
    return ssh_keys


@router.get("/{key_id}", response_model=SSHKeyPairResponse)
@handle_service_exceptions
async def get_ssh_key(
    key_id: int = Path(..., description="SSH key ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get SSH key details by ID."""
    ssh_key_repository = SSHKeyRepository(db)
    service = SSHKeyService(ssh_key_repository, db)
    ssh_key = await service.get_key_by_id(key_id)
    return ssh_key


@router.get("/{key_id}/public-key", response_model=SSHPublicKeyResponse)
@handle_service_exceptions
async def get_ssh_public_key(
    key_id: int = Path(..., description="SSH key ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """Export public key for deployment to remote hosts."""
    ssh_key_repository = SSHKeyRepository(db)
    service = SSHKeyService(ssh_key_repository, db)
    public_key = await service.get_public_key(key_id)
    return public_key


@router.put("/{key_id}", response_model=SSHKeyPairResponse)
@handle_service_exceptions
async def update_ssh_key(
    key_data: SSHKeyPairUpdate,
    key_id: int = Path(..., description="SSH key ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """Update SSH key metadata."""
    ssh_key_repository = SSHKeyRepository(db)
    service = SSHKeyService(ssh_key_repository, db)
    ssh_key = await service.update_key(key_id, key_data)
    return ssh_key


@router.delete("/{key_id}", status_code=204)
@handle_service_exceptions
async def delete_ssh_key(
    key_id: int = Path(..., description="SSH key ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """Delete an SSH key pair."""
    ssh_key_repository = SSHKeyRepository(db)
    service = SSHKeyService(ssh_key_repository, db)
    await service.delete_key(key_id)


@router.post("/{key_id}/rotate", response_model=SSHKeyPairResponse)
@handle_service_exceptions
async def rotate_ssh_key(
    key_id: int = Path(..., description="SSH key ID"),
    passphrase: Optional[str] = Query(
        None, description="Optional passphrase for new key"
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Rotate SSH key (generate new key pair with same metadata).

    This creates a completely new key pair while preserving the key's metadata.
    The old key material is replaced and cannot be recovered.
    """
    ssh_key_repository = SSHKeyRepository(db)
    service = SSHKeyService(ssh_key_repository, db)
    ssh_key = await service.rotate_key(key_id, passphrase)
    return ssh_key
