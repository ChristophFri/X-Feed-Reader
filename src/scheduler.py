"""Background scheduler and optional system-tray icon for X Feed Reader."""

import logging
import re
import threading
from typing import Callable

logger = logging.getLogger(__name__)

# Regex for interval strings like "30m", "6h", "1d"
_INTERVAL_RE = re.compile(r"^(\d+)\s*([mhd])$", re.IGNORECASE)

_UNIT_SECONDS = {
    "m": 60,
    "h": 3600,
    "d": 86400,
}


def parse_interval(interval_str: str) -> int:
    """
    Parse a human-friendly interval string into seconds.

    Supported formats: ``30m``, ``6h``, ``1d``

    Args:
        interval_str: Interval string to parse.

    Returns:
        Interval in seconds.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    match = _INTERVAL_RE.match(interval_str.strip())
    if not match:
        raise ValueError(
            f"Invalid interval '{interval_str}'. Use e.g. 30m, 6h, or 1d."
        )
    value = int(match.group(1))
    unit = match.group(2).lower()
    return value * _UNIT_SECONDS[unit]


def run_scheduler(
    interval: int,
    pipeline_func: Callable[[], None],
    interval_str: str,
    use_tray: bool = True,
) -> None:
    """
    Start a repeating scheduler that calls *pipeline_func* every *interval* seconds.

    If *use_tray* is ``True`` and ``pystray`` is available, a system-tray icon
    is shown (runs on the main thread, scheduler on a background thread).
    Otherwise, falls back to a simple console loop (``Ctrl+C`` to stop).

    Args:
        interval: Seconds between runs.
        pipeline_func: Zero-argument callable that executes the full pipeline.
        interval_str: Human-readable interval label (e.g. "6h") for display.
        use_tray: Whether to attempt showing a system-tray icon.
    """
    stop_event = threading.Event()

    def _scheduler_loop() -> None:
        while not stop_event.is_set():
            stop_event.wait(interval)
            if not stop_event.is_set():
                logger.info("Scheduled run triggered")
                try:
                    pipeline_func()
                except Exception:
                    logger.exception("Scheduled pipeline run failed")

    scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    scheduler_thread.start()

    if use_tray:
        try:
            _run_with_tray(
                on_run_now=pipeline_func,
                on_quit=lambda: stop_event.set(),
                interval_str=interval_str,
                stop_event=stop_event,
            )
            return  # tray loop exited normally
        except ImportError:
            logger.info("pystray not installed – falling back to console mode")
        except Exception:
            logger.exception("Failed to create tray icon – falling back to console mode")

    # Console fallback
    print(f"Scheduler running every {interval_str}. Press Ctrl+C to stop.")
    try:
        while not stop_event.is_set():
            stop_event.wait(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        scheduler_thread.join(timeout=5)
        print("Scheduler stopped.")


def _run_with_tray(
    on_run_now: Callable[[], None],
    on_quit: Callable[[], None],
    interval_str: str,
    stop_event: threading.Event,
) -> None:
    """
    Create and run a pystray system-tray icon (blocks on the main thread).

    Raises ImportError if pystray/Pillow are not installed.
    """
    import pystray  # type: ignore[import-untyped]
    from PIL import Image, ImageDraw  # type: ignore[import-untyped]

    # Generate a simple blue "X" icon (64x64)
    img = Image.new("RGB", (64, 64), color=(29, 155, 240))  # X/Twitter blue
    draw = ImageDraw.Draw(img)
    # Draw a white "X"
    draw.line((16, 16, 48, 48), fill="white", width=6)
    draw.line((48, 16, 16, 48), fill="white", width=6)

    def _on_run_now(icon: pystray.Icon, item: pystray.MenuItem) -> None:  # type: ignore[name-defined]
        threading.Thread(target=on_run_now, daemon=True).start()

    def _on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:  # type: ignore[name-defined]
        on_quit()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(f"Running every {interval_str}", None, enabled=False),
        pystray.MenuItem("Run Now", _on_run_now),
        pystray.MenuItem("Quit", _on_quit),
    )

    icon = pystray.Icon("xfeed", img, "XFeed Reader", menu)
    logger.info("System tray icon started")
    icon.run()  # blocks until icon.stop() is called
