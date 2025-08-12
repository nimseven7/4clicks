"""Service for SSH key management operations."""

import base64
import hashlib
import os
from typing import List, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.models import SSHKeyPair, SSHKeyType
from app.exceptions.exceptions import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    ServiceError,
    ValidationError,
)
from app.repositories.task_repository import SSHKeyRepository
from app.schemas.task_schema import (
    SSHKeyPairGenerate,
    SSHKeyPairImport,
    SSHKeyPairListResponse,
    SSHKeyPairResponse,
    SSHKeyPairUpdate,
    SSHPublicKeyResponse,
)


class SSHKeyService:
    """Service for SSH key pair management."""

    def __init__(self, ssh_key_repository: SSHKeyRepository, session: AsyncSession):
        self.ssh_key_repository = ssh_key_repository
        self.session = session
        self._encryption_key = self._get_encryption_key()

    def _get_encryption_key(self) -> bytes:
        """Get or create encryption key for private key storage."""
        # In production, this should be stored in environment variables or a secure key management system
        encryption_key = os.getenv("SSH_KEY_ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError("SSH_KEY_ENCRYPTION_KEY environment variable is required")

        # Ensure key is 32 bytes for AES-256
        return hashlib.sha256(encryption_key.encode()).digest()

    def _encrypt_private_key(
        self, private_key: str, passphrase: Optional[str] = None
    ) -> str:
        """Encrypt private key for storage."""
        # If passphrase is provided, use it as additional entropy
        key = self._encryption_key
        if passphrase:
            key = hashlib.sha256(key + passphrase.encode()).digest()

        # Generate random IV
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # Pad the private key to be multiple of 16 bytes
        padded_key = private_key.encode("utf-8")
        padding_length = 16 - (len(padded_key) % 16)
        padded_key += bytes([padding_length] * padding_length)

        encrypted_data = encryptor.update(padded_key) + encryptor.finalize()

        # Return base64 encoded IV + encrypted data
        return base64.b64encode(iv + encrypted_data).decode("utf-8")

    def _decrypt_private_key(
        self, encrypted_key: str, passphrase: Optional[str] = None
    ) -> str:
        """Decrypt private key from storage."""
        try:
            # Decode base64
            encrypted_data = base64.b64decode(encrypted_key.encode("utf-8"))

            # Extract IV and encrypted content
            iv = encrypted_data[:16]
            encrypted_content = encrypted_data[16:]

            # Use passphrase if provided
            key = self._encryption_key
            if passphrase:
                key = hashlib.sha256(key + passphrase.encode()).digest()

            cipher = Cipher(
                algorithms.AES(key), modes.CBC(iv), backend=default_backend()
            )
            decryptor = cipher.decryptor()

            padded_key = decryptor.update(encrypted_content) + decryptor.finalize()

            # Remove padding
            padding_length = padded_key[-1]
            private_key = padded_key[:-padding_length].decode("utf-8")

            return private_key
        except Exception as e:
            raise ValidationError(f"Failed to decrypt private key: {str(e)}")

    def _generate_ed25519_key_pair(
        self, passphrase: Optional[str] = None
    ) -> tuple[str, str]:
        """Generate ED25519 key pair."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        # Serialize private key
        encryption_algorithm: serialization.KeySerializationEncryption = (
            serialization.NoEncryption()
        )
        if passphrase:
            encryption_algorithm = serialization.BestAvailableEncryption(
                passphrase.encode()
            )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=encryption_algorithm,
        )

        # Serialize public key in SSH format
        public_ssh = public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )

        return private_pem.decode("utf-8"), public_ssh.decode("utf-8")

    def _generate_rsa_key_pair(
        self, key_size: int = 2048, passphrase: Optional[str] = None
    ) -> tuple[str, str]:
        """Generate RSA key pair."""
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=key_size, backend=default_backend()
        )
        public_key = private_key.public_key()

        # Serialize private key
        encryption_algorithm: serialization.KeySerializationEncryption = (
            serialization.NoEncryption()
        )
        if passphrase:
            encryption_algorithm = serialization.BestAvailableEncryption(
                passphrase.encode()
            )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=encryption_algorithm,
        )

        # Serialize public key in SSH format
        public_ssh = public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )

        return private_pem.decode("utf-8"), public_ssh.decode("utf-8")

    def _calculate_fingerprint(self, public_key: str) -> str:
        """Calculate SSH key fingerprint."""
        try:
            # Parse the public key
            key_parts = public_key.strip().split()
            if len(key_parts) < 2:
                raise ValueError("Invalid public key format")

            key_data = base64.b64decode(key_parts[1])
            digest = hashlib.sha256(key_data).digest()
            fingerprint = base64.b64encode(digest).decode("utf-8").rstrip("=")

            return f"SHA256:{fingerprint}"
        except Exception as e:
            raise ValidationError(f"Failed to calculate fingerprint: {str(e)}")

    async def generate_key_pair(
        self, key_data: SSHKeyPairGenerate
    ) -> SSHKeyPairResponse:
        """Generate a new SSH key pair."""
        try:
            # Check if key with same name already exists
            existing_key = await self.ssh_key_repository.get_by_name_and_project(
                key_data.name, key_data.project_name
            )
            if existing_key:
                raise EntityAlreadyExistsError(
                    f"SSH key '{key_data.name}' already exists in project '{key_data.project_name}'"
                )

            # Generate key pair based on type
            if key_data.key_type == SSHKeyType.ED25519:
                private_key, public_key = self._generate_ed25519_key_pair(
                    key_data.passphrase
                )
                key_size = None
            elif key_data.key_type == SSHKeyType.RSA:
                key_size = key_data.key_size or 2048
                if key_size not in [2048, 3072, 4096]:
                    raise ValidationError(
                        "RSA key size must be 2048, 3072, or 4096 bits"
                    )
                private_key, public_key = self._generate_rsa_key_pair(
                    key_size, key_data.passphrase
                )
            else:
                raise ValidationError(f"Unsupported key type: {key_data.key_type}")

            # Calculate fingerprint
            fingerprint = self._calculate_fingerprint(public_key)

            # Check if fingerprint already exists
            existing_fingerprint = await self.ssh_key_repository.get_by_fingerprint(
                fingerprint
            )
            if existing_fingerprint:
                raise EntityAlreadyExistsError(
                    "A key with this fingerprint already exists"
                )

            # Encrypt private key
            encrypted_private_key = self._encrypt_private_key(
                private_key, key_data.passphrase
            )

            # Create SSH key in database
            ssh_key_dict = {
                "name": key_data.name,
                "description": key_data.description,
                "project_name": key_data.project_name,
                "key_type": key_data.key_type,
                "key_size": key_size,
                "fingerprint": fingerprint,
                "private_key_encrypted": encrypted_private_key,
                "public_key": public_key,
                "passphrase_hint": key_data.passphrase_hint,
            }

            ssh_key = await self.ssh_key_repository.create(**ssh_key_dict)
            await self.session.flush()
            await self.session.refresh(ssh_key)
            await self.session.commit()

            return SSHKeyPairResponse.model_validate(ssh_key)

        except Exception as e:
            await self.session.rollback()
            if isinstance(e, (ValidationError, EntityAlreadyExistsError)):
                raise
            raise ServiceError(f"Failed to generate SSH key: {str(e)}")

    async def import_key_pair(self, key_data: SSHKeyPairImport) -> SSHKeyPairResponse:
        """Import an existing SSH key pair."""
        try:
            # Check if key with same name already exists
            existing_key = await self.ssh_key_repository.get_by_name_and_project(
                key_data.name, key_data.project_name
            )
            if existing_key:
                raise EntityAlreadyExistsError(
                    f"SSH key '{key_data.name}' already exists in project '{key_data.project_name}'"
                )

            try:
                # Parse private key to determine type and extract public key if not provided
                private_key_obj = serialization.load_ssh_private_key(
                    key_data.private_key.encode(),
                    password=(
                        key_data.passphrase.encode() if key_data.passphrase else None
                    ),
                    backend=default_backend(),
                )

                # Determine key type
                if isinstance(private_key_obj, ed25519.Ed25519PrivateKey):
                    key_type = SSHKeyType.ED25519
                    key_size = None
                elif isinstance(private_key_obj, rsa.RSAPrivateKey):
                    key_type = SSHKeyType.RSA
                    key_size = private_key_obj.key_size
                else:
                    raise ValidationError("Unsupported private key type")

                # Get public key if not provided
                if key_data.public_key:
                    public_key = key_data.public_key
                else:
                    public_key_obj = private_key_obj.public_key()
                    public_key = public_key_obj.public_bytes(
                        encoding=serialization.Encoding.OpenSSH,
                        format=serialization.PublicFormat.OpenSSH,
                    ).decode("utf-8")

            except Exception as e:
                raise ValidationError(f"Invalid private key: {str(e)}")

            # Calculate fingerprint
            fingerprint = self._calculate_fingerprint(public_key)

            # Check if fingerprint already exists
            existing_fingerprint = await self.ssh_key_repository.get_by_fingerprint(
                fingerprint
            )
            if existing_fingerprint:
                raise EntityAlreadyExistsError(
                    "A key with this fingerprint already exists"
                )

            # Encrypt private key
            encrypted_private_key = self._encrypt_private_key(
                key_data.private_key, key_data.passphrase
            )

            # Create SSH key in database
            ssh_key_dict = {
                "name": key_data.name,
                "description": key_data.description,
                "project_name": key_data.project_name,
                "key_type": key_type,
                "key_size": key_size,
                "fingerprint": fingerprint,
                "private_key_encrypted": encrypted_private_key,
                "public_key": public_key,
                "passphrase_hint": key_data.passphrase_hint,
            }

            ssh_key = await self.ssh_key_repository.create(**ssh_key_dict)
            await self.session.flush()
            await self.session.refresh(ssh_key)
            await self.session.commit()

            return SSHKeyPairResponse.model_validate(ssh_key)

        except Exception as e:
            await self.session.rollback()
            if isinstance(e, (ValidationError, EntityAlreadyExistsError)):
                raise
            raise ServiceError(f"Failed to import SSH key: {str(e)}")

    async def get_key_by_id(self, ssh_key_id: int) -> SSHKeyPairResponse:
        """Get SSH key by ID."""
        ssh_key = await self.ssh_key_repository.get_by_id(ssh_key_id)
        if not ssh_key:
            raise EntityNotFoundError(f"SSH key with ID {ssh_key_id} not found")

        return SSHKeyPairResponse.model_validate(ssh_key)

    async def get_public_key(self, ssh_key_id: int) -> SSHPublicKeyResponse:
        """Get public key for export."""
        ssh_key = await self.ssh_key_repository.get_by_id(ssh_key_id)
        if not ssh_key:
            raise EntityNotFoundError(f"SSH key with ID {ssh_key_id} not found")

        return SSHPublicKeyResponse(
            public_key=ssh_key.public_key,
            fingerprint=ssh_key.fingerprint,
            key_type=ssh_key.key_type,
        )

    async def get_decrypted_private_key(
        self, ssh_key_id: int, passphrase: Optional[str] = None
    ) -> str:
        """Get decrypted private key for task execution."""
        ssh_key = await self.ssh_key_repository.get_by_id(ssh_key_id)
        if not ssh_key:
            raise EntityNotFoundError(f"SSH key with ID {ssh_key_id} not found")

        if not ssh_key.is_active:
            raise ValidationError("SSH key is not active")

        # Update last used timestamp
        await self.ssh_key_repository.update_last_used(ssh_key_id)

        # Decrypt and return private key
        return self._decrypt_private_key(ssh_key.private_key_encrypted, passphrase)

    async def list_keys_by_project(
        self,
        project_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
    ) -> SSHKeyPairListResponse:
        """List SSH keys for a project."""
        ssh_keys = await self.ssh_key_repository.list_by_project(
            project_name, skip, limit, active_only
        )
        total = await self.ssh_key_repository.count_by_project(
            project_name, active_only
        )

        ssh_key_responses = [SSHKeyPairResponse.model_validate(key) for key in ssh_keys]

        return SSHKeyPairListResponse(ssh_keys=ssh_key_responses, total=total)

    async def update_key(
        self, ssh_key_id: int, key_data: SSHKeyPairUpdate
    ) -> SSHKeyPairResponse:
        """Update SSH key metadata."""
        try:
            # Check if key exists
            existing_key = await self.ssh_key_repository.get_by_id(ssh_key_id)
            if not existing_key:
                raise EntityNotFoundError(f"SSH key with ID {ssh_key_id} not found")

            # Check if new name conflicts with existing keys
            if key_data.name and key_data.name != existing_key.name:
                name_conflict = await self.ssh_key_repository.get_by_name_and_project(
                    key_data.name, existing_key.project_name
                )
                if name_conflict:
                    raise EntityAlreadyExistsError(
                        f"SSH key '{key_data.name}' already exists in project '{existing_key.project_name}'"
                    )

            updated_key = await self.ssh_key_repository.update(
                ssh_key_id, **key_data.model_dump(exclude_unset=True)
            )
            if not updated_key:
                raise EntityNotFoundError(f"SSH key with ID {ssh_key_id} not found")

            await self.session.commit()
            return SSHKeyPairResponse.model_validate(updated_key)

        except Exception as e:
            await self.session.rollback()
            if isinstance(e, (EntityNotFoundError, EntityAlreadyExistsError)):
                raise
            raise ServiceError(f"Failed to update SSH key: {str(e)}")

    async def delete_key(self, ssh_key_id: int) -> bool:
        """Delete SSH key."""
        try:
            success = await self.ssh_key_repository.delete(ssh_key_id)
            if not success:
                raise EntityNotFoundError(f"SSH key with ID {ssh_key_id} not found")

            await self.session.commit()
            return success

        except Exception as e:
            await self.session.rollback()
            if isinstance(e, EntityNotFoundError):
                raise
            raise ServiceError(f"Failed to delete SSH key: {str(e)}")

    async def rotate_key(
        self, ssh_key_id: int, passphrase: Optional[str] = None
    ) -> SSHKeyPairResponse:
        """Rotate SSH key (generate new key pair with same metadata)."""
        try:
            # Get existing key
            existing_key = await self.ssh_key_repository.get_by_id(ssh_key_id)
            if not existing_key:
                raise EntityNotFoundError(f"SSH key with ID {ssh_key_id} not found")

            # Generate new key pair of same type
            if existing_key.key_type == SSHKeyType.ED25519:
                private_key, public_key = self._generate_ed25519_key_pair(passphrase)
            elif existing_key.key_type == SSHKeyType.RSA:
                private_key, public_key = self._generate_rsa_key_pair(
                    existing_key.key_size or 2048, passphrase
                )
            else:
                raise ValidationError(f"Unsupported key type: {existing_key.key_type}")

            # Calculate new fingerprint
            fingerprint = self._calculate_fingerprint(public_key)

            # Check if new fingerprint already exists
            existing_fingerprint = await self.ssh_key_repository.get_by_fingerprint(
                fingerprint
            )
            if existing_fingerprint and existing_fingerprint.id != ssh_key_id:
                raise EntityAlreadyExistsError(
                    "Generated key conflicts with existing fingerprint"
                )

            # Encrypt new private key
            encrypted_private_key = self._encrypt_private_key(private_key, passphrase)

            # Update the existing key with new key material
            # (No metadata update needed, just key rotation)

            # Manually update key material (not in schema)
            from sqlalchemy import update as sql_update

            await self.session.execute(
                sql_update(SSHKeyPair)
                .where(SSHKeyPair.id == ssh_key_id)
                .values(
                    fingerprint=fingerprint,
                    private_key_encrypted=encrypted_private_key,
                    public_key=public_key,
                    passphrase_hint=None,
                )
            )

            # Get updated key
            updated_key = await self.ssh_key_repository.get_by_id(ssh_key_id)
            await self.session.commit()
            return SSHKeyPairResponse.model_validate(updated_key)

        except Exception as e:
            await self.session.rollback()
            if isinstance(
                e, (EntityNotFoundError, ValidationError, EntityAlreadyExistsError)
            ):
                raise
            raise ServiceError(f"Failed to rotate SSH key: {str(e)}")
