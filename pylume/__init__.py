"""
PyLume Python SDK - A client library for managing macOS VMs with PyLume.

Example:
    >>> from pylume import PyLume, VMConfig
    >>> client = PyLume()
    >>> config = VMConfig(
    ...     name="my-vm",
    ...     cpu=4,
    ...     memory="8GB",
    ...     disk_size="64GB"
    ... )
    >>> client.create_vm(config)
    >>> client.run_vm("my-vm")
"""

# Use relative imports
from .pylume import PyLume
from .models import (
    VMConfig,
    VMStatus,
    VMRunConfig,
    VMUpdateConfig,
    PullConfig,
    CloneConfig,
    SharedDirectory,
)
from .exceptions import (
    LumeError,
    LumeServerError,
    LumeConnectionError,
    LumeTimeoutError,
    LumeNotFoundError,
    LumeConfigError,
    LumeVMError,
    LumeImageError,
)

__version__ = "0.1.0"

__all__ = [
    "PyLume",
    "VMConfig",
    "VMStatus",
    "VMRunConfig",
    "VMUpdateConfig",
    "PullConfig",
    "CloneConfig",
    "SharedDirectory",
    "LumeError",
    "LumeServerError",
    "LumeConnectionError",
    "LumeTimeoutError",
    "LumeNotFoundError",
    "LumeConfigError",
    "LumeVMError",
    "LumeImageError",
]
