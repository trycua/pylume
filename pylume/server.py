import os
import time
import asyncio
import subprocess
import tempfile
import aiohttp
import logging
import socket
from typing import Optional, Tuple
import sys

class LumeServer:
    def __init__(self, debug: bool = False, server_start_timeout: int = 60):
        self.debug = debug
        self.server_start_timeout = server_start_timeout
        self.server_process: Optional[subprocess.Popen] = None
        self.output_file: Optional[tempfile.NamedTemporaryFile] = None
        self._output_task: Optional[asyncio.Task] = None
        self.port: Optional[int] = None
        self.base_url: Optional[str] = None
        
        # Configure logging
        self.logger = logging.getLogger('lume_server')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG if debug else logging.INFO)

    def _find_available_port(self, start_port: int = 3000) -> int:
        """Find the first available port starting from start_port."""
        port = start_port
        while port < 65535:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except OSError:
                port += 1
        raise RuntimeError("No available ports found")

    def _log_debug(self, message: str, **kwargs) -> None:
        """Log debug information if debug mode is enabled."""
        if self.debug:
            if kwargs:
                import json
                message = f"{message}\n{json.dumps(kwargs, indent=2)}"
            self.logger.debug(message)

    async def _read_output(self) -> None:
        """Read and display server output."""
        if not self.server_process:
            return

        while True:
            if self.server_process.poll() is not None:
                self.logger.debug("Server process ended")
                break

            # Read stdout
            if self.server_process.stdout:
                try:
                    line = self.server_process.stdout.readline()
                    if line:
                        line = line.strip()
                        if line:  # Only print non-empty lines
                            print(f"SERVER OUT: {line}")
                except Exception as e:
                    print(f"Error reading stdout: {e}")

            # Read stderr
            if self.server_process.stderr:
                try:
                    line = self.server_process.stderr.readline()
                    if line:
                        line = line.strip()
                        if line:  # Only print non-empty lines
                            print(f"SERVER ERR: {line}")
                except Exception as e:
                    print(f"Error reading stderr: {e}")

            await asyncio.sleep(0.1)

    async def ensure_running(self) -> None:
        """Ensure the lume server is running."""
        if self.server_process is None or self.server_process.poll() is not None:
            await self._start_server()

    async def _start_server(self) -> None:
        """Start the lume server."""
        self.logger.debug("Starting PyLume server")
        lume_path = os.path.join(os.path.dirname(__file__), "lume")
        if not os.path.exists(lume_path):
            raise RuntimeError(f"Could not find lume binary at {lume_path}")
        
        # Make sure the file is executable
        os.chmod(lume_path, 0o755)
        
        # Find an available port
        self.port = self._find_available_port()
        self.base_url = f"http://localhost:{self.port}/lume"
        
        # Create log file in the same directory as the lume binary
        log_file_path = os.path.abspath(os.path.join(os.path.dirname(lume_path), "lume_server.log"))
        
        if self.debug:
            print("\n=== Server Configuration ===")
            print(f"Log file path: {log_file_path}")
            print(f"Current directory: {os.getcwd()}")
            print(f"Lume binary path: {lume_path}")
            print(f"Server port: {self.port}")
            print("==========================\n")
        
        try:
            if self.debug:
                # In debug mode, write to log file
                self.logger.debug(f"Starting lume server with: {lume_path} serve --port {self.port}")
                
                # Open log file for both reading and writing
                self.output_file = open(log_file_path, 'w+')
                self.output_file.write(f"=== Starting Lume Server ===\n")
                self.output_file.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                self.output_file.write(f"Port: {self.port}\n")
                self.output_file.write("=========================\n\n")
                self.output_file.flush()
                
                # Start server process with output going to our managed file
                env = os.environ.copy()  # Copy current environment
                env.update({
                    "RUST_LOG": "debug",  # Enable Rust debug logging
                    "RUST_BACKTRACE": "1"  # Enable backtraces for better error reporting
                })
                
                self.server_process = subprocess.Popen(
                    [lume_path, "serve", "--port", str(self.port)],
                    stdout=self.output_file,
                    stderr=subprocess.STDOUT,  # Redirect stderr to stdout
                    cwd=os.path.dirname(lume_path),
                    start_new_session=True,
                    env=env
                )
                
                # Start log reading task
                async def tail_log():
                    while True:
                        try:
                            # Seek to current position
                            self.output_file.seek(0, os.SEEK_END)
                            
                            # Read any new content
                            line = self.output_file.readline()
                            if line:
                                line = line.strip()
                                if line:  # Only print non-empty lines
                                    print(f"SERVER: {line}")
                            
                            # Check if process is still running
                            if self.server_process.poll() is not None:
                                print("Server process ended")
                                break
                                
                            await asyncio.sleep(0.1)
                        except Exception as e:
                            print(f"Error reading log: {e}")
                            await asyncio.sleep(0.1)
                
                self._output_task = asyncio.create_task(tail_log())
                print(f"Started reading server logs from: {log_file_path}")
            else:
                # In non-debug mode, write to a temporary file
                self.output_file = tempfile.NamedTemporaryFile(mode='w+', delete=False)
                self.logger.debug(f"Using temporary file for server output: {self.output_file.name}")
                self.server_process = subprocess.Popen(
                    [lume_path, "serve", "--port", str(self.port)],
                    stdout=self.output_file,
                    stderr=self.output_file,
                    cwd=os.path.dirname(lume_path),
                    start_new_session=True
                )
                
        except Exception as e:
            await self._cleanup()
            raise RuntimeError(f"Failed to start lume server process: {str(e)}")
        
        await self._wait_for_server()

    async def _wait_for_server(self) -> None:
        """Wait for server to start and become responsive."""
        start_time = time.time()
        server_ready = False
        last_size = 0
        
        while time.time() - start_time < self.server_start_timeout:
            if self.server_process.poll() is not None:
                # Process has terminated
                error_msg = self._get_error_message()
                self._cleanup()
                raise RuntimeError(error_msg)
            
            server_ready = await self._check_server_output(last_size)
            if server_ready:
                break
            
            await asyncio.sleep(1.0)
        
        if not server_ready:
            self._cleanup()
            raise RuntimeError(
                f"Failed to start lume server after {self.server_start_timeout} seconds. "
                "Check the debug output for more details."
            )
        
        # Give the server a moment to fully initialize
        await asyncio.sleep(2.0)
        await self._verify_server()

    def _get_error_message(self) -> str:
        """Get error message from output file."""
        if not self.output_file:
            return "No output file available"
        self.output_file.seek(0)
        output = self.output_file.read()
        return (
            f"Server process terminated unexpectedly.\n"
            f"Exit code: {self.server_process.returncode}\n"
            f"Output: {output}"
        )

    async def _check_server_output(self, last_size: int) -> bool:
        """Check server output for startup message."""
        if self.debug:
            # In debug mode, just check server connection
            try:
                check_timeout = aiohttp.ClientTimeout(total=5.0)
                async with aiohttp.ClientSession(timeout=check_timeout) as check_client:
                    await check_client.get(f"{self.base_url}/vms")
                    self.logger.debug("Server is responding to requests")
                    return True
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
                return False
        else:
            # In non-debug mode, check the output file
            if not self.output_file:
                return False
                
            self.output_file.seek(0, os.SEEK_END)
            size = self.output_file.tell()
            if size > last_size:
                self.output_file.seek(last_size)
                new_output = self.output_file.read()
                if new_output.strip():
                    self.logger.debug(f"Server output: {new_output.strip()}")
                if "Server started" in new_output:
                    self.logger.debug("Server startup detected")
                    return True
                
            # Try to connect to the server
            try:
                check_timeout = aiohttp.ClientTimeout(total=5.0)
                async with aiohttp.ClientSession(timeout=check_timeout) as check_client:
                    await check_client.get(f"{self.base_url}/vms")
                    self.logger.debug("Server is responding to requests")
                    return True
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
                return False

    async def _verify_server(self) -> None:
        """Verify server is responding to requests."""
        try:
            check_timeout = aiohttp.ClientTimeout(total=10.0)
            async with aiohttp.ClientSession(timeout=check_timeout) as check_client:
                await check_client.get(f"{self.base_url}/vms")
                self.logger.debug("PyLume server started successfully")
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
            self.logger.error(f"Server verification failed: {str(e)}")
            self._cleanup()
            raise RuntimeError(f"Server started but is not responding: {str(e)}")

    async def _cleanup(self) -> None:
        """Clean up server process and output file."""
        if self._output_task and not self._output_task.done():
            self._output_task.cancel()
            try:
                await self._output_task
            except asyncio.CancelledError:
                pass
            self._output_task = None

        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            self.server_process = None
        
        if self.output_file:
            name = self.output_file.name
            self.output_file.close()
            # Only delete the output file if we're not in debug mode
            if not self.debug:
                try:
                    os.unlink(name)
                except Exception as e:
                    print(f"Error removing output file: {e}")
            else:
                print(f"\nServer log file preserved at: {name}")
            self.output_file = None

    async def stop(self) -> None:
        """Stop the server."""
        self.logger.debug("Stopping lume server...")
        await self._cleanup() 