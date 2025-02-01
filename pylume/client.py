import json
import asyncio
import aiohttp
from typing import Optional, Any, Dict

from .exceptions import (
    LumeError,
    LumeServerError,
    LumeConnectionError,
    LumeTimeoutError,
    LumeNotFoundError,
    LumeConfigError,
)

class LumeClient:
    def __init__(self, base_url: str, timeout: aiohttp.ClientTimeout, debug: bool = False):
        self.base_url = base_url
        self.timeout = timeout
        self.debug = debug
        self.session: Optional[aiohttp.ClientSession] = None

    def _log_debug(self, message: str, **kwargs) -> None:
        """Log debug information if debug mode is enabled."""
        if self.debug:
            print(f"DEBUG: {message}")
            if kwargs:
                print(json.dumps(kwargs, indent=2))

    async def _init_session(self) -> aiohttp.ClientSession:
        """Initialize aiohttp session if not already initialized."""
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session

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

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make a GET request."""
        try:
            session = await self._init_session()
            async with session.get(f"{self.base_url}{path}", params=params) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            raise await self._handle_api_error(e, f"GET {path}")

    async def post(self, path: str, data: Optional[Dict[str, Any]] = None, timeout: Optional[aiohttp.ClientTimeout] = None) -> Any:
        """Make a POST request."""
        try:
            session = await self._init_session()
            async with session.post(
                f"{self.base_url}{path}",
                headers={"Content-Type": "application/json"},
                json=data,
                timeout=timeout or self.timeout
            ) as response:
                response.raise_for_status()
                return await response.json() if response.content_length else None
        except Exception as e:
            raise await self._handle_api_error(e, f"POST {path}")

    async def patch(self, path: str, data: Dict[str, Any]) -> None:
        """Make a PATCH request."""
        try:
            session = await self._init_session()
            async with session.patch(
                f"{self.base_url}{path}",
                headers={"Content-Type": "application/json"},
                json=data
            ) as response:
                response.raise_for_status()
        except Exception as e:
            raise await self._handle_api_error(e, f"PATCH {path}")

    async def delete(self, path: str) -> None:
        """Make a DELETE request."""
        try:
            session = await self._init_session()
            async with session.delete(f"{self.base_url}{path}") as response:
                response.raise_for_status()
        except Exception as e:
            raise await self._handle_api_error(e, f"DELETE {path}")

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
        """Close the client session."""
        if self.session:
            await self.session.close()
            self.session = None 