"""PTY shell wrapper — spawns user's shell, proxies I/O, captures scrollback."""

import asyncio
import fcntl
import os
import pty
import signal
import struct
import sys
import termios
import tty


class ShellWrapper:
    """Spawns the user's $SHELL in a PTY and proxies I/O through asyncio."""

    def __init__(self, shell: str | None = None):
        self._shell = shell or os.environ.get("SHELL", "/bin/sh")
        self._master_fd: int = -1
        self._child_pid: int = -1
        self._original_termios: list | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False

        # Escape detection state machine (3-state)
        # IDLE → ESC_PENDING (300ms) → DOUBLE_ESC (200ms shortcut window)
        self._esc_pending = False
        self._double_esc_pending = False
        self._esc_timer: asyncio.TimerHandle | None = None
        self._shortcut_timer: asyncio.TimerHandle | None = None
        self._ESC_TIMEOUT = 0.3  # 300ms for single ESC
        self._SHORTCUT_TIMEOUT = 0.2  # 200ms for shortcut key after double-ESC

        # Mode flags
        self._ai_mode = False
        self._show_pty_output = False  # when True, show PTY output during AI mode

        # Callbacks for subclasses / composition
        self._on_master_output: list = []  # called with bytes from master_fd
        self._on_resize: list = []  # called with (rows, cols) on SIGWINCH
        self._ai_input_callback = None
        self._ai_mode_toggle_callback = None
        self._fix_it_callback = None
        self._explain_it_callback = None

    @property
    def master_fd(self) -> int:
        return self._master_fd

    @property
    def child_pid(self) -> int:
        return self._child_pid

    @property
    def ai_mode(self) -> bool:
        return self._ai_mode

    @ai_mode.setter
    def ai_mode(self, value: bool) -> None:
        self._ai_mode = value

    def add_master_output_callback(self, cb) -> None:
        """Register a callback that receives raw bytes from master_fd output."""
        self._on_master_output.append(cb)

    def set_ai_input_callback(self, cb) -> None:
        """Set callback for stdin data when in AI mode."""
        self._ai_input_callback = cb

    def set_ai_mode_toggle_callback(self, cb) -> None:
        """Set callback for AI mode toggle events. cb(entering: bool)."""
        self._ai_mode_toggle_callback = cb

    def add_resize_callback(self, cb) -> None:
        """Register a callback that receives (rows, cols) on terminal resize."""
        self._on_resize.append(cb)

    def set_fix_it_callback(self, cb) -> None:
        """Set callback for ESC-ESC-f shortcut."""
        self._fix_it_callback = cb

    def set_explain_it_callback(self, cb) -> None:
        """Set callback for ESC-ESC-e shortcut."""
        self._explain_it_callback = cb

    def set_show_pty_output(self, value: bool) -> None:
        """Enable/disable PTY output display during AI mode (for tool execution)."""
        self._show_pty_output = value

    def _get_terminal_size(self) -> tuple[int, int]:
        """Return (rows, cols) of the current terminal."""
        size = os.get_terminal_size()
        return size.lines, size.columns

    def _set_pty_size(self, rows: int, cols: int) -> None:
        """Set the PTY slave's terminal size."""
        if self._master_fd >= 0:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def spawn(self) -> None:
        """Fork a child process running the user's shell in a PTY."""
        self._master_fd, slave_fd = pty.openpty()

        # Set slave size to match current terminal
        rows, cols = self._get_terminal_size()
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        pid = os.fork()
        if pid == 0:
            # Child process
            os.close(self._master_fd)
            os.setsid()

            # Set up slave as controlling terminal
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

            # Redirect stdin/stdout/stderr to slave
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)

            # Exec the shell as an interactive (non-login) shell.
            # The user's terminal already ran login scripts; llaminal is a
            # sub-shell, so we want .bashrc / .zshrc / config.fish loaded.
            # -i forces interactive mode so rc file guards (e.g. $- check) pass.
            # Reset SHLVL so the shell thinks it's a fresh terminal session.
            os.environ["SHLVL"] = "0"
            shell_name = os.path.basename(self._shell)
            os.execv(self._shell, [shell_name, "-i"])
        else:
            # Parent process
            os.close(slave_fd)
            self._child_pid = pid

            # Save original terminal settings and enter raw mode
            self._original_termios = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())

    def _handle_sigwinch(self, signum, frame) -> None:
        """Forward terminal resize to the PTY child."""
        rows, cols = self._get_terminal_size()
        self._set_pty_size(rows, cols)
        # Forward SIGWINCH to child process group
        if self._child_pid > 0:
            try:
                os.kill(self._child_pid, signal.SIGWINCH)
            except ProcessLookupError:
                pass
        # Notify resize callbacks (e.g., pyte scrollback)
        for cb in self._on_resize:
            try:
                cb(rows, cols)
            except Exception:
                pass

    def _handle_sigchld(self, signum, frame) -> None:
        """Detect child exit."""
        try:
            pid, status = os.waitpid(self._child_pid, os.WNOHANG)
            if pid == self._child_pid:
                self._running = False
        except ChildProcessError:
            self._running = False

    def _on_stdin_ready(self) -> None:
        """Handle data available on stdin."""
        try:
            data = os.read(sys.stdin.fileno(), 4096)
        except OSError:
            return

        if not data:
            self._running = False
            return

        if self._ai_mode:
            # In AI mode, stdin is handled by the AI mode handler
            if self._ai_input_callback:
                self._ai_input_callback(data)
            return

        # Process each byte for escape detection
        self._process_stdin_bytes(data)

    def _process_stdin_bytes(self, data: bytes) -> None:
        """Process stdin bytes with 3-state escape detection.

        IDLE --[ESC]--> ESC_PENDING (300ms timer)
        ESC_PENDING --[ESC]--> DOUBLE_ESC (200ms shortcut timer)
        ESC_PENDING --[timeout]--> IDLE (flush ESC to shell)
        ESC_PENDING --[other]--> IDLE (flush ESC + byte to shell)
        DOUBLE_ESC --['f' within 200ms]--> fix_it_callback, IDLE
        DOUBLE_ESC --['e' within 200ms]--> explain_it_callback, IDLE
        DOUBLE_ESC --[timeout]--> enter AI mode, IDLE
        DOUBLE_ESC --[other]--> enter AI mode, IDLE
        """
        i = 0
        while i < len(data):
            byte = data[i : i + 1]
            i += 1

            if self._double_esc_pending:
                # In DOUBLE_ESC state — check for shortcut key
                self._cancel_shortcut_timer()
                self._double_esc_pending = False
                if byte == b"f" and self._fix_it_callback:
                    self._fix_it_callback()
                    return
                elif byte == b"e" and self._explain_it_callback:
                    self._explain_it_callback()
                    return
                else:
                    # Not a shortcut — enter normal AI mode
                    self._enter_ai_mode()
                    return
            elif byte == b"\x1b":
                if self._esc_pending:
                    # Second ESC within timeout → enter DOUBLE_ESC state
                    self._cancel_esc_timer()
                    self._esc_pending = False
                    self._double_esc_pending = True
                    self._start_shortcut_timer()
                    # Check if there are more bytes to consume for shortcut
                else:
                    # First ESC → start timer
                    self._esc_pending = True
                    self._start_esc_timer()
            else:
                if self._esc_pending:
                    # Non-ESC byte while waiting → forward the pending ESC + this byte
                    self._cancel_esc_timer()
                    self._esc_pending = False
                    remaining = b"\x1b" + data[i - 1 :]
                    self._write_to_master(remaining)
                    return
                else:
                    self._write_to_master(byte)

    def _start_esc_timer(self) -> None:
        """Start the 300ms timeout for single ESC."""
        if self._loop:
            self._esc_timer = self._loop.call_later(
                self._ESC_TIMEOUT, self._esc_timeout_fired
            )

    def _cancel_esc_timer(self) -> None:
        """Cancel the pending ESC timer."""
        if self._esc_timer is not None:
            self._esc_timer.cancel()
            self._esc_timer = None

    def _esc_timeout_fired(self) -> None:
        """Single ESC timeout expired — forward the ESC to shell."""
        self._esc_pending = False
        self._esc_timer = None
        self._write_to_master(b"\x1b")

    def _start_shortcut_timer(self) -> None:
        """Start the 200ms timeout for shortcut key after double-ESC."""
        if self._loop:
            self._shortcut_timer = self._loop.call_later(
                self._SHORTCUT_TIMEOUT, self._shortcut_timeout_fired
            )

    def _cancel_shortcut_timer(self) -> None:
        """Cancel the pending shortcut timer."""
        if self._shortcut_timer is not None:
            self._shortcut_timer.cancel()
            self._shortcut_timer = None

    def _shortcut_timeout_fired(self) -> None:
        """Shortcut window expired — enter normal AI mode."""
        self._double_esc_pending = False
        self._shortcut_timer = None
        self._enter_ai_mode()

    def _enter_ai_mode(self) -> None:
        """Enter AI mode via double-ESC."""
        self._ai_mode = True
        if self._ai_mode_toggle_callback:
            self._ai_mode_toggle_callback(True)

    def exit_ai_mode(self) -> None:
        """Exit AI mode (called by AIMode or externally)."""
        self._ai_mode = False

    def _write_to_master(self, data: bytes) -> None:
        """Write data to the master PTY fd."""
        if self._master_fd >= 0:
            try:
                os.write(self._master_fd, data)
            except OSError:
                pass

    def _on_master_ready(self) -> None:
        """Handle data available on master_fd (shell output)."""
        try:
            data = os.read(self._master_fd, 4096)
        except OSError:
            self._running = False
            return

        if not data:
            self._running = False
            return

        # Write to stdout (user sees shell output)
        # Suppress during AI mode unless PTY tool execution is active
        if not self._ai_mode or self._show_pty_output:
            try:
                os.write(sys.stdout.fileno(), data)
            except OSError:
                pass

        # Notify callbacks (e.g., pyte scrollback capture) — always active
        for cb in self._on_master_output:
            try:
                cb(data)
            except Exception:
                pass

    async def run(self) -> None:
        """Run the asyncio event loop proxying I/O between stdin/stdout and the PTY."""
        self._loop = asyncio.get_running_loop()
        self._running = True

        # Install signal handlers
        old_sigwinch = signal.signal(signal.SIGWINCH, self._handle_sigwinch)
        old_sigchld = signal.signal(signal.SIGCHLD, self._handle_sigchld)

        # Register fd readers
        self._loop.add_reader(sys.stdin.fileno(), self._on_stdin_ready)
        self._loop.add_reader(self._master_fd, self._on_master_ready)

        try:
            # Wait until the shell exits
            while self._running:
                await asyncio.sleep(0.1)
        finally:
            self._loop.remove_reader(sys.stdin.fileno())
            self._loop.remove_reader(self._master_fd)
            signal.signal(signal.SIGWINCH, old_sigwinch)
            signal.signal(signal.SIGCHLD, old_sigchld)

    def cleanup(self) -> None:
        """Restore terminal and clean up resources."""
        # Restore original terminal settings
        if self._original_termios is not None:
            try:
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, self._original_termios
                )
            except (termios.error, OSError):
                pass
            self._original_termios = None

        # Close master fd
        if self._master_fd >= 0:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = -1

        # Wait for child
        if self._child_pid > 0:
            try:
                os.waitpid(self._child_pid, os.WNOHANG)
            except ChildProcessError:
                pass
            self._child_pid = -1

    def write_to_shell(self, data: bytes) -> None:
        """Public method to write data to the shell's stdin."""
        self._write_to_master(data)
