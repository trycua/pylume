import os
import sys
import json
import time
import httpx
import asyncio
import subprocess
from typing import Optional, List, Union

# Handle both package imports and direct module execution
try:
    from .models import (
        VMConfig,
        VMStatus,
        VMRunConfig,
        VMUpdateConfig,
        PullConfig,
        CloneConfig,
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
except ImportError:
    # For direct module execution
    from models import (
        VMConfig,
        VMStatus,
        VMRunConfig,
        VMUpdateConfig,
        PullConfig,
        CloneConfig,
        SharedDirectory,
        ImageList,
    )
    from exceptions import (
        LumeError,
        LumeServerError,
        LumeConnectionError,
        LumeTimeoutError,
        LumeNotFoundError,
        LumeConfigError,
        LumeVMError,
        LumeImageError,
    )

class PyLume:
    def __init__(
        self,
        port: int = 3000,
        timeout: int = 6000,
        auto_start_server: bool = True,
        debug: bool = False
    ):
        """Initialize the async PyLume client.
        
        Args:
            port: The port to use for the PyLume API server
            timeout: Request timeout in seconds
            auto_start_server: Whether to automatically start the lume server if not running
            debug: Enable debug logging
        """
        self.port = port
        self.base_url = f"http://localhost:{port}/lume"
        self.timeout = timeout
        self.debug = debug
        self.client = httpx.AsyncClient(timeout=timeout)
        self.server_process = None
        
        if auto_start_server:
            asyncio.create_task(self._ensure_server_running())
    
    def _log_debug(self, message: str, **kwargs) -> None:
        """Log debug information if debug mode is enabled."""
        if self.debug:
            print(f"DEBUG: {message}")
            if kwargs:
                print(json.dumps(kwargs, indent=2))

    async def _handle_api_error(self, e: httpx.HTTPError, operation: str) -> None:
        """Handle API errors and raise appropriate custom exceptions."""
        if isinstance(e, httpx.ConnectError):
            raise LumeConnectionError(f"Failed to connect to PyLume server: {str(e)}")
        elif isinstance(e, httpx.ReadTimeout) or isinstance(e, httpx.WriteTimeout):
            raise LumeTimeoutError(f"Request timed out: {str(e)}")
            
        if not hasattr(e, 'response') or e.response is None:
            raise LumeServerError(f"Unknown error during {operation}: {str(e)}")
            
        status_code = e.response.status_code
        response_text = e.response.text
        
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

    async def _ensure_server_running(self) -> None:
        """Ensure the lume server is running, start it if it's not."""
        try:
            self._log_debug("Checking if lume server is running...")
            # Try to connect to the server
            await self.client.get(f"{self.base_url}/vms")
            self._log_debug("PyLume server is running")
        except httpx.ConnectError:
            self._log_debug("PyLume server not running, attempting to start it")
            # Server not running, try to start it
            lume_path = os.path.join(os.path.dirname(__file__), "lume")
            if not os.path.exists(lume_path):
                raise RuntimeError(f"Could not find lume binary at {lume_path}")
            
            # Make sure the file is executable
            os.chmod(lume_path, 0o755)
            
            # Start the server
            self._log_debug(f"Starting lume server with: {lume_path} serve --port {self.port}")
            
            # Start server in background using subprocess.Popen
            self.server_process = subprocess.Popen(
                [lume_path, "serve", "--port", str(self.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(lume_path),
                start_new_session=True  # Run in new session to avoid blocking
            )
            
            # Start output reader task
            asyncio.create_task(self._read_output())
            
            # Wait for server to start (max 10 seconds)
            start_time = time.time()
            while time.time() - start_time < 10:
                if self.server_process.poll() is not None:
                    # Process has terminated
                    raise RuntimeError(f"Server process terminated unexpectedly")
                
                try:
                    await self.client.get(f"{self.base_url}/vms")
                    self._log_debug("PyLume server started successfully")
                    break
                except httpx.ConnectError:
                    self._log_debug(f"Waiting for server to start ({int(time.time() - start_time)}s/10s)")
                    await asyncio.sleep(0.5)
            else:
                # Kill the process if it didn't start in time
                if self.server_process:
                    self.server_process.terminate()
                raise RuntimeError("Failed to start lume server after 10 seconds")

    async def _read_output(self) -> None:
        """Read and log server output."""
        while True:
            if not self.server_process or self.server_process.poll() is not None:
                break

            # Read stdout
            stdout_line = self.server_process.stdout.readline() if self.server_process.stdout else None
            if stdout_line:
                self._log_debug(f"Server: {stdout_line.decode().strip()}")

            # Read stderr
            stderr_line = self.server_process.stderr.readline() if self.server_process.stderr else None
            if stderr_line:
                self._log_debug(f"Server: {stderr_line.decode().strip()}")

            await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning

    async def create_vm(self, config: Union[VMConfig, dict]) -> None:
        """Create a new VM."""
        if isinstance(config, dict):
            config = VMConfig(**config)
            
        self._log_debug("Creating VM", config=config.model_dump())
        
        try:
            # Create payload excluding ipsw if None
            payload = config.model_dump()
            if payload.get('ipsw') is None:
                del payload['ipsw']
                
            response = await self.client.post(
                f"{self.base_url}/vms",
                json=payload
            )
            response.raise_for_status()
            self._log_debug("VM created successfully")
        except httpx.HTTPError as e:
            raise LumeVMError("Failed to create VM") from await self._handle_api_error(e, "create VM")

    async def run_vm(self, name: str, config: Optional[Union[VMRunConfig, dict]] = None) -> None:
        """Run a VM."""
        if isinstance(config, dict):
            config = VMRunConfig(**config)
            
        self._log_debug(
            f"Running VM {name}",
            config=config.model_dump() if config else None
        )
        
        try:
            data = config.model_dump() if config else None
            response = await self.client.post(
                f"{self.base_url}/vms/{name}/run",
                json=data,
            )
            response.raise_for_status()
            self._log_debug(f"VM {name} started successfully")
        except httpx.HTTPError as e:
            raise LumeVMError(f"Failed to run VM {name}") from await self._handle_api_error(e, "run VM")

    async def list_vms(self) -> List[VMStatus]:
        """List all VMs."""
        self._log_debug("Listing VMs")
        
        try:
            response = await self.client.get(f"{self.base_url}/vms")
            response.raise_for_status()
            data = response.json()
            self._log_debug("Retrieved VM list", vms=data)
            return [VMStatus.model_validate(vm) for vm in data]
        except httpx.HTTPError as e:
            raise LumeVMError("Failed to list VMs") from await self._handle_api_error(e, "list VMs")

    async def get_vm(self, name: str) -> VMStatus:
        """Get VM details."""
        self._log_debug(f"Getting details for VM {name}")
        
        try:
            response = await self.client.get(f"{self.base_url}/vms/{name}")
            response.raise_for_status()
            data = response.json()
            self._log_debug(f"Retrieved VM {name} details", vm=data)
            return VMStatus.model_validate(data)
        except httpx.HTTPError as e:
            raise LumeVMError(f"Failed to get VM {name}") from await self._handle_api_error(e, "get VM")

    async def update_vm(self, name: str, config: Union[VMUpdateConfig, dict]) -> None:
        """Update VM settings."""
        if isinstance(config, dict):
            config = VMUpdateConfig(**config)
            
        self._log_debug(f"Updating VM {name}", config=config.model_dump(exclude_none=True))
        
        try:
            response = await self.client.patch(
                f"{self.base_url}/vms/{name}",
                json=config.model_dump(exclude_none=True),
            )
            response.raise_for_status()
            self._log_debug(f"VM {name} updated successfully")
        except httpx.HTTPError as e:
            raise LumeVMError(f"Failed to update VM {name}") from await self._handle_api_error(e, "update VM")

    async def stop_vm(self, name: str) -> None:
        """Stop a VM."""
        self._log_debug(f"Stopping VM {name}")
        
        try:
            response = await self.client.post(f"{self.base_url}/vms/{name}/stop")
            response.raise_for_status()
            self._log_debug(f"VM {name} stopped successfully")
        except httpx.HTTPError as e:
            raise LumeVMError(f"Failed to stop VM {name}") from await self._handle_api_error(e, "stop VM")

    async def delete_vm(self, name: str) -> None:
        """Delete a VM."""
        self._log_debug(f"Deleting VM {name}")
        
        try:
            response = await self.client.delete(f"{self.base_url}/vms/{name}")
            response.raise_for_status()
            self._log_debug(f"VM {name} deleted successfully")
        except httpx.HTTPError as e:
            raise LumeVMError(f"Failed to delete VM {name}") from await self._handle_api_error(e, "delete VM")

    async def pull_image(self, config: Union[PullConfig, dict]) -> None:
        """Pull a VM image."""
        if isinstance(config, dict):
            config = PullConfig(**config)
            
        self._log_debug("Pulling image config", config=config.model_dump())
        
        # Format the payload to match the API's expectations
        payload = {
            "image": f"{config.image}:{config.tag}",
        }
        if config.name:
            payload["name"] = config.name
            
        self._log_debug("Sending pull request", payload=payload)
        
        try:
            response = await self.client.post(
                f"{self.base_url}/pull",
                json=payload,
            )
            response.raise_for_status()
            self._log_debug("Image pulled successfully")
        except httpx.HTTPError as e:
            raise LumeImageError("Failed to pull image") from await self._handle_api_error(e, "pull image")

    async def clone_vm(self, name: str, new_name: str) -> None:
        """Clone a VM."""
        self._log_debug(f"Cloning VM {name} to {new_name}")
        
        try:
            config = CloneConfig(name=name, new_name=new_name)
            response = await self.client.post(
                f"{self.base_url}/vms/{name}/clone",
                json=config.model_dump(),
            )
            response.raise_for_status()
            self._log_debug(f"VM {name} cloned to {new_name} successfully")
        except httpx.HTTPError as e:
            raise LumeVMError(f"Failed to clone VM {name}") from await self._handle_api_error(e, "clone VM")

    async def get_latest_ipsw_url(self) -> str:
        """Get the latest IPSW URL."""
        self._log_debug("Getting latest IPSW URL")
        
        try:
            response = await self.client.get(f"{self.base_url}/ipsw")
            response.raise_for_status()
            url = response.json()["url"]
            self._log_debug("Retrieved latest IPSW URL", url=url)
            return url
        except httpx.HTTPError as e:
            raise LumeServerError("Failed to get latest IPSW URL") from await self._handle_api_error(e, "get IPSW URL")

    async def get_images(self, organization: Optional[str] = None) -> ImageList:
        """Get list of available images.
        
        Args:
            organization: Optional organization to filter images by. Defaults to None (uses trycua).
        
        Returns:
            ImageList: List of available images.
            
        Raises:
            LumeImageError: If there's an error getting the image list.
        """
        self._log_debug("Getting image list", organization=organization)
        
        try:
            params = {}
            if organization:
                params['organization'] = organization
                
            response = await self.client.get(
                f"{self.base_url}/images",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            self._log_debug("Retrieved image list", images=data)
            return ImageList.model_validate(data)
        except httpx.HTTPError as e:
            raise LumeImageError("Failed to get image list") from await self._handle_api_error(e, "get images")

    async def close(self) -> None:
        """Close the client and cleanup resources."""
        await self.client.aclose()
        if self.server_process:
            self.server_process.terminate()
            await self.server_process.wait()

    async def __aenter__(self) -> 'PyLume':
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close() 