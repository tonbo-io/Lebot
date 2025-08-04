import logging
import subprocess
import os
import tempfile
import signal
import time
from typing import Dict, Any
from .base import Tool


class Bash(Tool):
    """Bash tool implementation for executing shell commands with persistent session."""

    def __init__(self, timeout: int = 30):
        """Initialize the bash tool with optional timeout.

        Args:
            timeout: Maximum execution time in seconds (default 30)
        """
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        self.session_env = os.environ.copy()
        self.working_dir = os.getcwd()
        self.session_active = True

    def get_schema(self) -> Dict[str, Any]:
        """Return the bash tool schema for Anthropic's API."""
        # Note: Bash uses Anthropic's built-in tool type
        return {"type": "bash_20250124", "name": "bash"}

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute a bash command.

        Args:
            **kwargs: Keyword arguments:
                - command (str): The bash command to execute
                - restart (bool): Whether to restart the bash session

        Returns:
            Dict with stdout, stderr, exit_code, and any error messages
        """
        command = kwargs.get("command", "")
        restart = kwargs.get("restart", False)

        if restart:
            self._restart_session()

        if not self.session_active:
            return {
                "stdout": "",
                "stderr": "Session has been terminated. Use restart=true to start a new session.",
                "exit_code": 1,
                "error": "Session terminated",
            }

        # Security: Basic command validation (can be extended)
        if self._is_dangerous_command(command):
            return {
                "stdout": "",
                "stderr": "Command blocked for security reasons",
                "exit_code": 1,
                "error": "Security block",
            }

        try:
            # Create a temporary script file to preserve session state
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as script_file:
                # Write session preservation logic
                script_file.write("#!/bin/bash\n")
                script_file.write(f"cd '{self.working_dir}'\n")
                script_file.write(f"{command}\n")
                script_file.write("LAST_EXIT_CODE=$?\n")  # Capture exit code immediately
                script_file.write("echo '___PWD___'\n")
                script_file.write("pwd\n")
                script_file.write("echo '___EXIT_CODE___'\n")
                script_file.write("echo $LAST_EXIT_CODE\n")
                script_file.flush()

                # Execute the command
                process = subprocess.Popen(
                    ["bash", script_file.name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=self.session_env,
                    text=True,
                    preexec_fn=os.setsid,  # Create new process group for timeout handling
                )

                try:
                    stdout, stderr = process.communicate(timeout=self.timeout)
                    exit_code = process.returncode
                except subprocess.TimeoutExpired:
                    # Kill the process group
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    time.sleep(0.5)  # Give it time to terminate
                    if process.poll() is None:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    stdout, stderr = process.communicate()
                    return {
                        "stdout": stdout,
                        "stderr": f"Command timed out after {self.timeout} seconds\n{stderr}",
                        "exit_code": -1,
                        "error": "Timeout",
                    }
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(script_file.name)
                    except:
                        pass

                # Parse the output to extract PWD and actual exit code
                stdout_lines = stdout.split("\n")
                actual_stdout = []
                new_pwd = None
                actual_exit_code = exit_code

                i = 0
                while i < len(stdout_lines):
                    if stdout_lines[i] == "___PWD___" and i + 1 < len(stdout_lines):
                        new_pwd = stdout_lines[i + 1]
                        i += 2
                    elif stdout_lines[i] == "___EXIT_CODE___" and i + 1 < len(stdout_lines):
                        try:
                            actual_exit_code = int(stdout_lines[i + 1])
                        except ValueError:
                            pass
                        i += 2
                    else:
                        actual_stdout.append(stdout_lines[i])
                        i += 1

                # Update working directory if changed
                if new_pwd and os.path.exists(new_pwd):
                    self.working_dir = new_pwd

                # Truncate output if too large (similar to Claude's behavior)
                final_stdout = "\n".join(actual_stdout).rstrip()
                if len(final_stdout) > 50000:  # 50KB limit
                    final_stdout = final_stdout[:50000] + "\n... (output truncated)"

                if len(stderr) > 10000:  # 10KB limit for errors
                    stderr = stderr[:10000] + "\n... (error output truncated)"

                # Log the command execution
                self.logger.info(f"Executed command: {command[:100]}{'...' if len(command) > 100 else ''}")

                return {"stdout": final_stdout, "stderr": stderr, "exit_code": actual_exit_code, "error": None}

        except Exception as e:
            self.logger.exception(f"Failed to execute command: {e}")
            return {"stdout": "", "stderr": str(e), "exit_code": -1, "error": f"Execution failed: {e}"}

    def _restart_session(self):
        """Restart the bash session."""
        self.session_env = os.environ.copy()
        self.working_dir = os.getcwd()
        self.session_active = True
        self.logger.info("Bash session restarted")

    def _is_dangerous_command(self, command: str) -> bool:
        """Check if a command is potentially dangerous.

        Args:
            command: The command to check

        Returns:
            True if the command is considered dangerous
        """
        # Basic security checks - can be extended
        dangerous_patterns = [
            "rm -rf /",
            "dd if=/dev/zero",
            ":(){ :|:& };:",  # Fork bomb
            "mkfs.",
            "format ",
        ]

        command_lower = command.lower().strip()
        for pattern in dangerous_patterns:
            if pattern.lower() in command_lower:
                self.logger.warning(f"Blocked dangerous command: {command[:50]}...")
                return True

        return False
