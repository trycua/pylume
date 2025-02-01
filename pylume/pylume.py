import os
import sys
import json
import time
import aiohttp
import asyncio
import subprocess
from typing import Optional, List, Union, Callable, TypeVar, Any
from functools import wraps
import re

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
        auto_start_server: bool = True,
        server_start_timeout: int = 60
    ):
        """Initialize the async PyLume client.
        
        Args:
            debug: Enable debug logging
            auto_start_server: Whether to automatically start the lume server if not running
            server_start_timeout: Timeout in seconds to wait for server to start
        """
        self.server = LumeServer(debug=debug, server_start_timeout=server_start_timeout)
        self.client = None  # Will be initialized after server starts
        self.auto_start_server = auto_start_server

    async def __aenter__(self) -> 'PyLume':
        """Async context manager entry."""
        if self.auto_start_server:
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
            client_timeout = aiohttp.ClientTimeout(
                total=float(300),  # 5 minutes total timeout
                connect=30.0,
                sock_read=float(300),
                sock_connect=30.0
            )
            self.client = LumeClient(base_url=self.server.base_url, timeout=client_timeout, debug=self.server.debug)

    @ensure_server
    async def _ensure_client(self) -> None:
        """Ensure client is initialized."""
        if self.client is None:
            await self._init_client()

    def _log_debug(self, message: str, **kwargs) -> None:
        """Log debug information if debug mode is enabled."""
        if self.server.debug:
            print(f"DEBUG: {message}")
            if kwargs:
                print(json.dumps(kwargs, indent=2))

    async def _handle_api_error(self, e: Exception, operation: str) -> None:
        """Handle API errors and raise appropriate custom exceptions."""
        if isinstance(e, aiohttp.ClientConnectionError):
            raise LumeConnectionError(f"Failed to connect to PyLume server: {str(e)}")
        elif isinstance(e, asyncio.TimeoutError):
            raise LumeTimeoutError(f"Request timed out: {str(e)}")
            
        if not hasattr(e, 'status') and not isinstance(e, aiohttp.ClientResponseError):
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

    async def _ensure_server_running(self) -> None:
        """Ensure the lume server is running, start it if it's not."""
        try:
            self._log_debug("Checking if lume server is running...")
            # Try to connect to the server with a short timeout
            check_timeout = aiohttp.ClientTimeout(
                total=10.0,
                connect=5.0,
                sock_read=5.0,
                sock_connect=5.0
            )
            async with aiohttp.ClientSession(timeout=check_timeout) as check_client:
                await check_client.get(f"{self.server.base_url}/vms")
                self._log_debug("PyLume server is running")
                return
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError, RuntimeError):
            self._log_debug("PyLume server not running, attempting to start it")
            # Server not running, try to start it
            lume_path = os.path.join(os.path.dirname(__file__), "lume")
            if not os.path.exists(lume_path):
                raise RuntimeError(f"Could not find lume binary at {lume_path}")
            
            # Make sure the file is executable
            os.chmod(lume_path, 0o755)
            
            # Create a temporary file for server output
            import tempfile
            output_file = tempfile.NamedTemporaryFile(mode='w+', delete=False)
            self._log_debug(f"Using temporary file for server output: {output_file.name}")
            
            # Start the server
            self._log_debug(f"Starting lume server with: {lume_path} serve --port {self.server.port}")
            
            # Start server in background using subprocess.Popen
            try:
                self.server_process = subprocess.Popen(
                    [lume_path, "serve", "--port", str(self.server.port)],
                    stdout=output_file,
                    stderr=output_file,
                    cwd=os.path.dirname(lume_path),
                    start_new_session=True  # Run in new session to avoid blocking
                )
            except Exception as e:
                output_file.close()
                os.unlink(output_file.name)
                raise RuntimeError(f"Failed to start lume server process: {str(e)}")
            
            # Wait for server to start
            self._log_debug(f"Waiting up to {self.server.server_start_timeout} seconds for server to start...")
            start_time = time.time()
            server_ready = False
            last_size = 0
            
            while time.time() - start_time < self.server.server_start_timeout:
                if self.server_process.poll() is not None:
                    # Process has terminated
                    output_file.seek(0)
                    output = output_file.read()
                    output_file.close()
                    os.unlink(output_file.name)
                    error_msg = (
                        f"Server process terminated unexpectedly.\n"
                        f"Exit code: {self.server_process.returncode}\n"
                        f"Output: {output}"
                    )
                    raise RuntimeError(error_msg)
                
                # Check output file for server ready message
                output_file.seek(0, os.SEEK_END)
                size = output_file.tell()
                if size > last_size:  # Only read if there's new content
                    output_file.seek(last_size)
                    new_output = output_file.read()
                    if new_output.strip():  # Only log non-empty output
                        self._log_debug(f"Server output: {new_output.strip()}")
                    last_size = size
                    
                    if "Server started" in new_output:
                        server_ready = True
                        self._log_debug("Server startup detected")
                        break
                
                # Try to connect to the server periodically
                try:
                    check_timeout = aiohttp.ClientTimeout(total=5.0)  # Create proper timeout object
                    async with aiohttp.ClientSession(timeout=check_timeout) as check_client:
                        await check_client.get(f"{self.server.base_url}/vms")
                        server_ready = True
                        self._log_debug("Server is responding to requests")
                        break
                except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
                    pass  # Server not ready yet
                
                await asyncio.sleep(1.0)  # Increased from 0.5 to 1.0
            
            if not server_ready:
                # Cleanup if server didn't start
                if self.server_process:
                    self.server_process.terminate()
                    try:
                        self.server_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.server_process.kill()
                output_file.close()
                os.unlink(output_file.name)
                raise RuntimeError(
                    f"Failed to start lume server after {self.server.server_start_timeout} seconds. "
                    "Check the debug output for more details."
                )
            
            # Give the server a moment to fully initialize
            await asyncio.sleep(2.0)
            
            # Verify server is responding
            try:
                check_timeout = aiohttp.ClientTimeout(total=10.0)  # Create proper timeout object
                async with aiohttp.ClientSession(timeout=check_timeout) as check_client:
                    await check_client.get(f"{self.server.base_url}/vms")
                    self._log_debug("PyLume server started successfully")
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                self._log_debug(f"Server verification failed: {str(e)}")
                if self.server_process:
                    self.server_process.terminate()
                    try:
                        self.server_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.server_process.kill()
                output_file.close()
                os.unlink(output_file.name)
                raise RuntimeError(f"Server started but is not responding: {str(e)}")
            
            # Store output file for future reference
            self.output_file = output_file
            self._log_debug("Server startup completed successfully")

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
        await self._ensure_client()
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
        
        # Use a longer timeout for pull requests
        pull_timeout = aiohttp.ClientTimeout(
            total=300.0,
            connect=30.0,
            sock_read=300.0,
            sock_connect=30.0
        )
        
        self.client.print_curl("POST", "/pull", payload)
        await self.client.post("/pull", payload, timeout=pull_timeout)

    @ensure_server
    async def clone_vm(self, name: str, new_name: str) -> None:
        """Clone a VM with the given name to a new VM with new_name."""
        config = CloneSpec(name=name, newName=new_name)
        self.client.print_curl("POST", "/vms/clone", config.model_dump())
        await self.client.post("/vms/clone", config.model_dump())

    @ensure_server
    async def get_latest_ipsw_url(self) -> str:
        """Get the latest IPSW URL."""
        await self._ensure_client()
        data = await self.client.get("/ipsw")
        return data["url"]

    @ensure_server
    async def get_images(self, organization: Optional[str] = None) -> ImageList:
        """Get list of available images."""
        await self._ensure_client()
        params = {"organization": organization} if organization else None
        data = await self.client.get("/images", params)
        return ImageList(root=data)

    async def close(self) -> None:
        """Close the client and stop the server."""
        await self.client.close()
        await asyncio.sleep(2)  # Give the server 2 seconds to finish any pending operations
        await self.server.stop()

    @ensure_server
    async def _ensure_client(self) -> None:
        """Ensure client is initialized."""
        if self.client is None:
            await self._init_client()

    @ensure_server
    async def get_latest_ipsw_url(self) -> str:
        """Get the latest IPSW URL."""
        await self._ensure_client()
        data = await self.client.get("/ipsw")
        return data["url"]

    @ensure_server
    async def get_images(self, organization: Optional[str] = None) -> ImageList:
        """Get list of available images."""
        await self._ensure_client()
        params = {"organization": organization} if organization else None
        data = await self.client.get("/images", params)
        return ImageList(root=data) 