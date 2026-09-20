"""Application exception hierarchy."""


class GrafIdError(Exception):
    """Base exception for Graf-Id runtime errors."""


class ConfigError(GrafIdError):
    """Raised when configuration is missing, invalid, or unreadable."""


class DatabaseError(GrafIdError):
    """Raised when the database cannot be opened, initialized, or verified."""


class GrafPermissionError(GrafIdError):
    """Raised when the app lacks filesystem permissions."""


class StartupError(GrafIdError):
    """Raised when startup cannot complete successfully."""


class ProjectError(GrafIdError):
    """Raised when project registry operations fail."""


class ValidationError(ProjectError):
    """Raised when project input or path validation fails."""


class DuplicateProjectError(ProjectError):
    """Raised when a project name or path already exists."""


class ScanError(GrafIdError):
    """Raised when a project scan cannot be completed."""


class SnapshotError(GrafIdError):
    """Raised when scan snapshot persistence or retrieval fails."""


class SessionError(GrafIdError):
    """Raised when work session lifecycle operations fail."""


class ResumeError(GrafIdError):
    """Raised when resume generation or persistence fails."""
