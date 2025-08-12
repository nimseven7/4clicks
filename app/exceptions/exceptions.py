"""Application-specific exceptions with HTTP status code mapping."""

from typing import Optional


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(AppException):
    """Exception raised when validation fails."""

    def __init__(self, message: str = "Validation error."):
        super().__init__(message, status_code=400)


class EntityNotFoundError(AppException):
    """Exception raised when an entity is not found."""

    def __init__(self, message: str = "Entity not found."):
        super().__init__(message, status_code=404)


class EntityAlreadyExistsError(AppException):
    """Exception raised when an entity already exists."""

    def __init__(self, message: str = "Entity already exists."):
        super().__init__(message, status_code=409)


class PermissionDeniedError(AppException):
    """Exception raised when operation is not permitted."""

    def __init__(self, message: str = "Operation not permitted."):
        super().__init__(message, status_code=403)


class ServiceError(AppException):
    """Exception raised for general service errors."""

    def __init__(self, message: str = "Service error.", status_code: int = 500):
        super().__init__(message, status_code)


class RepositoryError(AppException):
    """Exception raised for repository/database errors."""

    def __init__(self, message: str = "Database error.", status_code: int = 500):
        super().__init__(message, status_code)


# Legacy exceptions for backward compatibility
class TerraformNotInitializedError(ServiceError):
    """Exception raised when Terraform is not initialized."""

    def __init__(self, message: str = "Terraform is not initialized."):
        super().__init__(message, status_code=400)


class TerraformInitError(ServiceError):
    """Exception raised when Terraform initialization fails."""

    def __init__(self, message: str = "Terraform initialization failed."):
        super().__init__(message, status_code=500)
