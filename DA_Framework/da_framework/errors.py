"""Exception hierarchy for the MAIZSIM IES framework."""


class DAFrameworkError(Exception):
    """Base class for framework errors."""


class ConfigError(DAFrameworkError):
    """Raised when the TOML configuration is missing or invalid."""


class ObservationError(DAFrameworkError):
    """Raised when observation data cannot be read or validated."""


class OutputReadError(DAFrameworkError):
    """Raised when MAIZSIM outputs cannot be mapped to observations."""


class ParameterWriteError(DAFrameworkError):
    """Raised when model parameter files cannot be updated."""


class ModelRunError(DAFrameworkError):
    """Raised when MAIZSIM cannot be launched or required inputs are missing."""


class WorkflowError(DAFrameworkError):
    """Raised when the IES workflow cannot proceed."""
