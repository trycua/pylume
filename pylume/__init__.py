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

# Import all models first
from .models import (
    VMConfig,
    VMStatus,
    VMRunOpts,
    VMUpdateOpts,
    ImageRef,
    CloneSpec,
    SharedDirectory,
    ImageList,
    ImageInfo,
)

# Import exceptions
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

# Import main class last to avoid circular imports
from .pylume import PyLume

__version__ = "0.1.0"

__all__ = [
    "PyLume",
    "VMConfig",
    "VMStatus",
    "VMRunOpts",
    "VMUpdateOpts",
    "ImageRef",
    "CloneSpec",
    "SharedDirectory",
    "ImageList",
    "ImageInfo",
    "LumeError",
    "LumeServerError",
    "LumeConnectionError",
    "LumeTimeoutError",
    "LumeNotFoundError",
    "LumeConfigError",
    "LumeVMError",
    "LumeImageError",
]
