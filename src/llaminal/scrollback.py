"""Scrollback capture — pyte HistoryScreen for rolling terminal history."""

import re

import pyte

# Patterns that indicate progress bar / download lines
_PROGRESS_PATTERNS = [
    re.compile(r"\[#+"),           # [####
    re.compile(r"\d+%\s*\|[=▮█]"),  # 50% |===  or 50% |▮▮▮
    re.compile(r"\d+%\s*━"),       # rich-style progress
    re.compile(r"Downloading.*\d+%"),
    re.compile(r"Uploading.*\d+%"),
    re.compile(r"\r.*\d+%"),       # carriage-return progress
]


def _is_progress_line(line: str) -> bool:
    return any(p.search(line) for p in _PROGRESS_PATTERNS)


def _compress(lines: list[str]) -> list[str]:
    """Apply smart compression to scrollback lines."""
    result: list[str] = []

    # 1. Collapse progress bar runs
    i = 0
    while i < len(lines):
        if _is_progress_line(lines[i]):
            first = lines[i]
            j = i + 1
            while j < len(lines) and _is_progress_line(lines[j]):
                j += 1
            count = j - i
            last = lines[j - 1]
            if count > 2:
                result.append(first)
                result.append(f"... ({count - 2} lines of progress output) ...")
                result.append(last)
            else:
                result.extend(lines[i:j])
            i = j
        else:
            result.append(lines[i])
            i += 1

    # 2. Truncate large output blocks (>80 consecutive non-blank lines)
    compressed: list[str] = []
    i = 0
    while i < len(result):
        if result[i]:  # non-blank
            block_start = i
            while i < len(result) and result[i]:
                i += 1
            block_len = i - block_start
            if block_len > 80:
                compressed.extend(result[block_start : block_start + 20])
                compressed.append(f"... ({block_len - 40} lines truncated) ...")
                compressed.extend(result[i - 20 : i])
            else:
                compressed.extend(result[block_start:i])
        else:
            compressed.append(result[i])
            i += 1

    # 3. Dedup blank line runs
    final: list[str] = []
    prev_blank = False
    for line in compressed:
        if not line:
            if not prev_blank:
                final.append(line)
            prev_blank = True
        else:
            prev_blank = False
            final.append(line)

    return final


class ScrollbackCapture:
    """Captures terminal output into a pyte HistoryScreen for AI context."""

    def __init__(self, cols: int, rows: int, history_size: int = 5000):
        self._cols = cols
        self._rows = rows
        self._screen = pyte.HistoryScreen(cols, rows, history=history_size)
        self._screen.set_mode(pyte.modes.LNM)
        self._stream = pyte.Stream(self._screen)

    def feed(self, data: bytes) -> None:
        """Feed raw bytes from master_fd output into the pyte screen."""
        try:
            self._stream.feed(data.decode("utf-8", errors="replace"))
        except Exception:
            pass

    def resize(self, rows: int, cols: int) -> None:
        """Update screen dimensions (called on SIGWINCH)."""
        self._cols = cols
        self._rows = rows
        self._screen.resize(rows, cols)

    def get_context(self, max_lines: int = 200) -> str | None:
        """Extract scrollback history + visible screen as context text.

        Applies smart compression (progress bar collapse, large block truncation,
        blank line dedup) then caps at `max_lines` from the bottom.
        """
        lines = self._history_lines() + self._screen_lines()

        # Trim trailing empty lines
        while lines and not lines[-1]:
            lines.pop()

        if not lines:
            return None

        # Apply compression
        lines = _compress(lines)

        # Cap at max_lines from the bottom (most recent)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]

        text = "\n".join(lines).strip()
        return text if text else None

    def _history_lines(self) -> list[str]:
        """Extract text lines from scrolled-off history."""
        result = []
        for row in self._screen.history.top:
            line = "".join(
                row[col].data for col in range(self._cols)
            ).rstrip()
            result.append(line)
        return result

    def _screen_lines(self) -> list[str]:
        """Extract text lines from the visible screen."""
        return [line.rstrip() for line in self._screen.display]
