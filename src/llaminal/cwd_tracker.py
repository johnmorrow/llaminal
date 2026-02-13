"""Track the working directory of the child shell process."""

import os
import subprocess
import sys
import time


class CwdTracker:
    """Cross-platform cwd tracking for a child process."""

    def __init__(self, child_pid: int):
        self._pid = child_pid
        self._cached_cwd: str | None = None
        self._cache_time: float = 0.0
        self._cache_ttl = 1.0  # seconds

    def get_cwd(self) -> str | None:
        """Return the child process's current working directory, or None on failure."""
        now = time.monotonic()
        if self._cached_cwd and (now - self._cache_time) < self._cache_ttl:
            return self._cached_cwd

        cwd = self._read_cwd()
        if cwd:
            self._cached_cwd = cwd
            self._cache_time = now
        return cwd

    def _read_cwd(self) -> str | None:
        if sys.platform == "linux":
            return self._read_cwd_linux()
        elif sys.platform == "darwin":
            return self._read_cwd_macos()
        return None

    def _read_cwd_linux(self) -> str | None:
        try:
            return os.readlink(f"/proc/{self._pid}/cwd")
        except OSError:
            return None

    def _read_cwd_macos(self) -> str | None:
        try:
            result = subprocess.run(
                ["lsof", "-p", str(self._pid), "-Fn"],
                capture_output=True, text=True, timeout=2,
            )
            # Parse: look for 'fcwd' line, then next 'n' line is the path
            lines = result.stdout.splitlines()
            found_cwd = False
            for line in lines:
                if line == "fcwd":
                    found_cwd = True
                elif found_cwd and line.startswith("n"):
                    return line[1:]  # strip the 'n' prefix
            return None
        except (subprocess.TimeoutExpired, OSError):
            return None
