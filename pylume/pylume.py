import os
import sys
import json
import time
import asyncio
import subprocess
from typing import Optional, List, Union, Callable, TypeVar, Any
from functools import wraps
import re
import signal

from .server import LumeServer
from .client import LumeClient
from .models import (
    VMConfig,
    VMStatus,
    VMRunOpts,
    VMUpdateOpts,
    ImageRef,
    CloneSpec,
    SharedDirectory,
    ImageList,
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

# Type variable for the decorator
T = TypeVar('T')

def ensure_server(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to ensure server is running before executing the method."""
    @wraps(func)
    async def wrapper(self: 'PyLume', *args: Any, **kwargs: Any) -> T:
        await self.server.ensure_running()
        return await func(self, *args, **kwargs)
    return wrapper

class PyLume:
    def __init__(
        self,
        debug: bool = False,
        server_start_timeout: int = 60,
        port: Optional[int] = None,
        use_existing_server: bool = False
    ):
        """Initialize the async PyLume client.
        
        Args:
            debug: Enable debug logging
            auto_start_server: Whether to automatically start the lume server if not running
            server_start_timeout: Timeout in seconds to wait for server to start
            port: Port number for the lume server. Required when use_existing_server is True.
            use_existing_server: If True, will try to connect to an existing server on the specified port
                               instead of starting a new one.
        """
        if use_existing_server and port is None:
            raise LumeConfigError("Port must be specified when using an existing server")
        
        self.server = LumeServer(
            debug=debug, 
            server_start_timeout=server_start_timeout,
            port=port,
            use_existing_server=use_existing_server
        )
        self.client = None

    async def __aenter__(self) -> 'PyLume':
        """Async context manager entry."""
        if self.server.use_existing_server:
            # Just set up the base URL and initialize client for existing server
            self.server.port = self.server.requested_port
            self.server.base_url = f"http://localhost:{self.server.port}/lume"
        else:
            await self.server.ensure_running()
        
        await self._init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self.client is not None:
            await self.client.close()
        await self.server.stop()

    async def _init_client(self) -> None:
        """Initialize the client if not already initialized."""
        if self.client is None:
            if self.server.base_url is None:
                raise RuntimeError("Server base URL not set")
            self.client = LumeClient(
                base_url=self.server.base_url,
                timeout=300.0,
                debug=self.server.debug
            )

    def _log_debug(self, message: str, **kwargs) -> None:
        """Log debug information if debug mode is enabled."""
        if self.server.debug:
            print(f"DEBUG: {message}")
            if kwargs:
                print(json.dumps(kwargs, indent=2))

    async def _handle_api_error(self, e: Exception, operation: str) -> None:
        """Handle API errors and raise appropriate custom exceptions."""
        if isinstance(e, subprocess.SubprocessError):
            raise LumeConnectionError(f"Failed to connect to PyLume server: {str(e)}")
        elif isinstance(e, asyncio.TimeoutError):
            raise LumeTimeoutError(f"Request timed out: {str(e)}")
            
        if not hasattr(e, 'status') and not isinstance(e, subprocess.CalledProcessError):
            raise LumeServerError(f"Unknown error during {operation}: {str(e)}")
            
        status_code = getattr(e, 'status', 500)
        response_text = str(e)
        
        self._log_debug(
            f"{operation} request failed",
            status_code=status_code,
            response_text=response_text
        )
        
        if status_code == 404:
            raise LumeNotFoundError(f"Resource not found during {operation}")
        elif status_code == 400:
            raise LumeConfigError(f"Invalid configuration for {operation}: {response_text}")
        elif status_code >= 500:
            raise LumeServerError(
                f"Server error during {operation}",
                status_code=status_code,
                response_text=response_text
            )
        else:
            raise LumeServerError(
                f"Error during {operation}",
                status_code=status_code,
                response_text=response_text
            )

    async def _read_output(self) -> None:
        """Read and log server output."""
        try:
            while True:
                if not self.server_process or self.server_process.poll() is not None:
                    self._log_debug("Server process ended")
                    break

                # Read stdout without blocking
                if self.server_process.stdout:
                    while True:
                        line = self.server_process.stdout.readline()
                        if not line:
                            break
                        line = line.strip()
                        self._log_debug(f"Server stdout: {line}")
                        if "Server started" in line:
                            self._log_debug("Detected server started message")
                            return

                # Read stderr without blocking
                if self.server_process.stderr:
                    while True:
                        line = self.server_process.stderr.readline()
                        if not line:
                            break
                        line = line.strip()
                        self._log_debug(f"Server stderr: {line}")
                        if "error" in line.lower():
                            raise RuntimeError(f"Server error: {line}")

                await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning
        except Exception as e:
            self._log_debug(f"Error in output reader: {str(e)}")
            raise

    @ensure_server
    async def create_vm(self, spec: Union[VMConfig, dict]) -> None:
        """Create a new VM."""
        if isinstance(spec, VMConfig):
            spec = spec.model_dump(by_alias=True, exclude_none=True)
        
        self.client.print_curl("POST", "/vms", spec)
        await self.client.post("/vms", spec)

    @ensure_server
    async def run_vm(self, name: str, opts: Optional[Union[VMRunOpts, dict]] = None) -> None:
        """Run a VM."""
        if opts is None:
            opts = VMRunOpts(no_display=False)
        elif isinstance(opts, dict):
            opts = VMRunOpts(**opts)
            
        payload = opts.model_dump(by_alias=True, exclude_none=True)
        self.client.print_curl("POST", f"/vms/{name}/run", payload)
        await self.client.post(f"/vms/{name}/run", payload)

    @ensure_server
    async def list_vms(self) -> List[VMStatus]:
        """List all VMs."""
        data = await self.client.get("/vms")
        return [VMStatus.model_validate(vm) for vm in data]

    @ensure_server
    async def get_vm(self, name: str) -> VMStatus:
        """Get VM details."""
        data = await self.client.get(f"/vms/{name}")
        return VMStatus.model_validate(data)

    @ensure_server
    async def update_vm(self, name: str, params: Union[VMUpdateOpts, dict]) -> None:
        """Update VM settings."""
        if isinstance(params, dict):
            params = VMUpdateOpts(**params)
            
        payload = params.model_dump(by_alias=True, exclude_none=True)
        self.client.print_curl("PATCH", f"/vms/{name}", payload)
        await self.client.patch(f"/vms/{name}", payload)

    @ensure_server
    async def stop_vm(self, name: str) -> None:
        """Stop a VM."""
        await self.client.post(f"/vms/{name}/stop")

    @ensure_server
    async def delete_vm(self, name: str) -> None:
        """Delete a VM."""
        await self.client.delete(f"/vms/{name}")

    @ensure_server
    async def pull_image(self, spec: Union[ImageRef, dict, str], name: Optional[str] = None) -> None:
        """Pull a VM image."""
        await self._init_client()
        if isinstance(spec, str):
            if ":" in spec:
                image_str = spec
            else:
                image_str = f"{spec}:latest"
            registry = "ghcr.io"
            organization = "trycua"
        elif isinstance(spec, dict):
            image = spec.get("image", "")
            tag = spec.get("tag", "latest")
            image_str = f"{image}:{tag}"
            registry = spec.get("registry", "ghcr.io")
            organization = spec.get("organization", "trycua")
        else:
            image_str = f"{spec.image}:{spec.tag}"
            registry = spec.registry
            organization = spec.organization
            
        payload = {
            "image": image_str,
            "name": name,
            "registry": registry,
            "organization": organization
        }
        
        self.client.print_curl("POST", "/pull", payload)
        await self.client.post("/pull", payload, timeout=300.0)

    @ensure_server
    async def clone_vm(self, name: str, new_name: str) -> None:
        """Clone a VM with the given name to a new VM with new_name."""
        config = CloneSpec(name=name, newName=new_name)
        self.client.print_curl("POST", "/vms/clone", config.model_dump())
        await self.client.post("/vms/clone", config.model_dump())

    @ensure_server
    async def get_latest_ipsw_url(self) -> str:
        """Get the latest IPSW URL."""
        await self._init_client()
        data = await self.client.get("/ipsw")
        return data["url"]

    @ensure_server
    async def get_images(self, organization: Optional[str] = None) -> ImageList:
        """Get list of available images."""
        await self._init_client()
        params = {"organization": organization} if organization else None
        data = await self.client.get("/images", params)
        return ImageList(root=data)

    async def close(self) -> None:
        """Close the client and stop the server."""
        if self.client is not None:
            await self.client.close()
            self.client = None
        await asyncio.sleep(1)  # Reduced from 2 to 1 second
        await self.server.stop()

    async def _ensure_client(self) -> None:
        """Ensure client is initialized."""
        if self.client is None:
            await self._init_client() 