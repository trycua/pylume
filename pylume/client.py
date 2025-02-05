import json
import asyncio
import subprocess
from typing import Optional, Any, Dict
import shlex

from .exceptions import (
    LumeError,
    LumeServerError,
    LumeConnectionError,
    LumeTimeoutError,
    LumeNotFoundError,
    LumeConfigError,
)

class LumeClient:
    def __init__(self, base_url: str, timeout: float = 60.0, debug: bool = False):
        self.base_url = base_url
        self.timeout = timeout
        self.debug = debug

    def _log_debug(self, message: str, **kwargs) -> None:
        """Log debug information if debug mode is enabled."""
        if self.debug:
            print(f"DEBUG: {message}")
            if kwargs:
                print(json.dumps(kwargs, indent=2))

    async def _run_curl(self, method: str, path: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a curl command and return the response."""
        url = f"{self.base_url}{path}"
        if params:
            param_str = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{param_str}"

        cmd = ["curl", "-X", method, "-s", "-w", "%{http_code}", "-m", str(self.timeout)]
        
        if data is not None:
            cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
        
        cmd.append(url)
        
        self._log_debug(f"Running curl command: {' '.join(map(shlex.quote, cmd))}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise LumeConnectionError(f"Curl command failed: {stderr.decode()}")
            
            # The last 3 characters are the status code
            response = stdout.decode()
            status_code = int(response[-3:])
            response_body = response[:-3]  # Remove status code from response
            
            if status_code >= 400:
                if status_code == 404:
                    raise LumeNotFoundError(f"Resource not found: {path}")
                elif status_code == 400:
                    raise LumeConfigError(f"Invalid request: {response_body}")
                elif status_code >= 500:
                    raise LumeServerError(f"Server error: {response_body}")
                else:
                    raise LumeError(f"Request failed with status {status_code}: {response_body}")
            
            return json.loads(response_body) if response_body.strip() else None
            
        except asyncio.TimeoutError:
            raise LumeTimeoutError(f"Request timed out after {self.timeout} seconds")

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make a GET request."""
        return await self._run_curl("GET", path, params=params)

    async def post(self, path: str, data: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Any:
        """Make a POST request."""
        old_timeout = self.timeout
        if timeout is not None:
            self.timeout = timeout
        try:
            return await self._run_curl("POST", path, data=data)
        finally:
            self.timeout = old_timeout

    async def patch(self, path: str, data: Dict[str, Any]) -> None:
        """Make a PATCH request."""
        await self._run_curl("PATCH", path, data=data)

    async def delete(self, path: str) -> None:
        """Make a DELETE request."""
        await self._run_curl("DELETE", path)

    def print_curl(self, method: str, path: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Print equivalent curl command for debugging."""
        curl_cmd = f"""curl -X {method} \\
  '{self.base_url}{path}'"""
        
        if data:
            curl_cmd += f" \\\n  -H 'Content-Type: application/json' \\\n  -d '{json.dumps(data)}'"
        
        print("\nEquivalent curl command:")
        print(curl_cmd)
        print()

    async def close(self) -> None:
        """Close the client resources."""
        pass  # No shared resources to clean up