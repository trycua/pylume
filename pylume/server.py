import os
import time
import asyncio
import subprocess
import tempfile
import aiohttp
import logging
import socket
from typing import Optional
import sys
from .exceptions import LumeConnectionError
import signal

class LumeServer:
    def __init__(
        self, 
        debug: bool = False, 
        server_start_timeout: int = 60,
        port: Optional[int] = None,
        use_existing_server: bool = False
    ):
        """Initialize the LumeServer."""
        self.debug = debug
        self.server_start_timeout = server_start_timeout
        self.server_process = None
        self.output_file = None
        self.requested_port = port
        self.port = None
        self.base_url = None
        self.use_existing_server = use_existing_server
        
        # Configure logging
        self.logger = logging.getLogger('lume_server')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG if debug else logging.INFO)

    def _check_port_available(self, port: int) -> bool:
        """Check if a specific port is available."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return True
        except OSError:
            return False

    def _get_server_port(self) -> int:
        """Get and validate the server port.
        
        Returns:
            int: The validated port number
            
        Raises:
            RuntimeError: If no port was specified
            LumeConfigError: If the requested port is not available
        """
        if self.requested_port is None:
            raise RuntimeError("No port specified for lume server")
        
        if not self._check_port_available(self.requested_port):
            from .exceptions import LumeConfigError
            raise LumeConfigError(f"Requested port {self.requested_port} is not available")
        
        return self.requested_port

    async def _start_server(self) -> None:
        """Start the lume server using a managed shell script."""
        self.logger.debug("Starting PyLume server")
        lume_path = os.path.join(os.path.dirname(__file__), "lume")
        if not os.path.exists(lume_path):
            raise RuntimeError(f"Could not find lume binary at {lume_path}")
        
        script_file = None
        try:
            os.chmod(lume_path, 0o755)
            self.port = self._get_server_port()
            self.base_url = f"http://localhost:{self.port}/lume"
            
            # Create shell script with trap for process management
            script_content = f"""#!/bin/bash
trap 'kill $(jobs -p)' EXIT
exec {lume_path} serve --port {self.port}
"""
            script_dir = os.path.dirname(lume_path)
            script_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.sh',
                dir=script_dir,
                delete=True
            )
            script_file.write(script_content)
            script_file.flush()
            os.chmod(script_file.name, 0o755)
            
            # Set up output handling - just use a temp file
            self.output_file = tempfile.NamedTemporaryFile(mode='w+', delete=False)
            
            # Start the managed server process
            env = os.environ.copy()
            env["RUST_BACKTRACE"] = "1"
            
            self.server_process = subprocess.Popen(
                ['/bin/bash', script_file.name],
                stdout=self.output_file,
                stderr=subprocess.STDOUT,
                cwd=script_dir,
                env=env
            )

            # Wait for server to initialize
            await asyncio.sleep(2)
            await self._wait_for_server()

        except Exception as e:
            await self._cleanup()
            raise RuntimeError(f"Failed to start lume server process: {str(e)}")
        finally:
            # Ensure script file is cleaned up
            if script_file:
                try:
                    script_file.close()
                except:
                    pass

    async def _tail_log(self) -> None:
        """Read and display server log output in debug mode."""
        while True:
            try:
                self.output_file.seek(0, os.SEEK_END)
                line = self.output_file.readline()
                if line:
                    line = line.strip()
                    if line:
                        print(f"SERVER: {line}")
                if self.server_process.poll() is not None:
                    print("Server process ended")
                    break
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Error reading log: {e}")
                await asyncio.sleep(0.1)

    async def _wait_for_server(self) -> None:
        """Wait for server to start and become responsive with increased timeout."""
        start_time = time.time()
        while time.time() - start_time < self.server_start_timeout:
            if self.server_process.poll() is not None:
                error_msg = await self._get_error_output()
                await self._cleanup()
                raise RuntimeError(error_msg)
            
            try:
                await self._verify_server()
                self.logger.debug("Server is now responsive")
                return
            except Exception as e:
                self.logger.debug(f"Server not ready yet: {str(e)}")
                await asyncio.sleep(1.0)
        
        await self._cleanup()
        raise RuntimeError(f"Server failed to start after {self.server_start_timeout} seconds")

    async def _verify_server(self) -> None:
        """Verify server is responding to requests."""
        try:
            timeout = aiohttp.ClientTimeout(total=10.0)
            async with aiohttp.ClientSession(timeout=timeout) as client:
                await client.get(f"{self.base_url}/vms")
                self.logger.debug("PyLume server started successfully")
        except Exception as e:
            raise RuntimeError(f"Server not responding: {str(e)}")

    async def _get_error_output(self) -> str:
        """Get error output from the server process."""
        if not self.output_file:
            return "No output available"
        self.output_file.seek(0)
        output = self.output_file.read()
        return (
            f"Server process terminated unexpectedly.\n"
            f"Exit code: {self.server_process.returncode}\n"
            f"Output: {output}"
        )

    async def _cleanup(self) -> None:
        """Clean up all server resources."""
        if self.server_process:
            try:
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.server_process.kill()
            except:
                pass
            self.server_process = None

        # Clean up output file
        if self.output_file:
            try:
                self.output_file.close()
                os.unlink(self.output_file.name)
            except Exception as e:
                self.logger.debug(f"Error cleaning up output file: {e}")
            self.output_file = None

    async def ensure_running(self) -> None:
        """Start the server if we're managing it."""
        if not self.use_existing_server:
            await self._start_server()

    async def stop(self) -> None:
        """Stop the server if we're managing it."""
        if not self.use_existing_server:
            self.logger.debug("Stopping lume server...")
            await self._cleanup() 