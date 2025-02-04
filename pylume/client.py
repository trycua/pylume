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

    def _create_connector(self) -> aiohttp.TCPConnector:
        """Create a new connector for each session."""
        return aiohttp.TCPConnector(
            force_close=True,
            enable_cleanup_closed=True,
            keepalive_timeout=None,
            limit=10
        )

    def _log_debug(self, message: str, **kwargs) -> None:
        """Log debug information if debug mode is enabled."""
        if self.debug:
            print(f"DEBUG: {message}")
            if kwargs:
                print(json.dumps(kwargs, indent=2))

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make a GET request."""
        connector = self._create_connector()
        async with aiohttp.ClientSession(
            timeout=self.timeout,
            connector=connector,
            headers={'Connection': 'close'}
        ) as session:
            try:
                async with session.get(f"{self.base_url}{path}", params=params) as response:
                    response.raise_for_status()
                    return await response.json()
            finally:
                await connector.close()

    async def post(self, path: str, data: Optional[Dict[str, Any]] = None, timeout: Optional[aiohttp.ClientTimeout] = None) -> Any:
        """Make a POST request."""
        connector = self._create_connector()
        async with aiohttp.ClientSession(
            timeout=timeout or self.timeout,
            connector=connector,
            headers={
                'Content-Type': 'application/json',
                'Connection': 'close'
            }
        ) as session:
            try:
                async with session.post(
                    f"{self.base_url}{path}",
                    json=data
                ) as response:
                    response.raise_for_status()
                    return await response.json() if response.content_length else None
            finally:
                await connector.close()

    async def patch(self, path: str, data: Dict[str, Any]) -> None:
        """Make a PATCH request."""
        connector = self._create_connector()
        async with aiohttp.ClientSession(
            timeout=self.timeout,
            connector=connector,
            headers={
                'Content-Type': 'application/json',
                'Connection': 'close'
            }
        ) as session:
            try:
                async with session.patch(f"{self.base_url}{path}", json=data) as response:
                    response.raise_for_status()
            finally:
                await connector.close()

    async def delete(self, path: str) -> None:
        """Make a DELETE request."""
        connector = self._create_connector()
        async with aiohttp.ClientSession(
            timeout=self.timeout,
            connector=connector,
            headers={'Connection': 'close'}
        ) as session:
            try:
                async with session.delete(f"{self.base_url}{path}") as response:
                    response.raise_for_status()
            finally:
                await connector.close()

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