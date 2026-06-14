"""Background photo provider for the dashboard slideshow.

Reads images from a local/network folder (PHOTO_DIR). Maintains a shuffled
deck of all discovered files so every photo is shown before any repeats.
Pre-decodes one photo at a time on a background thread so next_surface()
returns immediately without blocking the render loop.
"""
import logging
import os
import random
import threading
import time
from datetime import datetime

import pygame

from config import (
    PHOTO_DIR, PHOTO_RESCAN_MINUTES, PHOTO_CACHE_SIZE,
    SCREEN_WIDTH, SCREEN_HEIGHT,
)

logger = logging.getLogger(__name__)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
ERROR_BACKOFF = 30


def _fit(surface: pygame.Surface) -> pygame.Surface:
    """Scale a decoded photo to fit within the canvas, preserving aspect."""
    w, h = surface.get_size()
    if w <= 0 or h <= 0:
        return surface
    scale = min(SCREEN_WIDTH / w, SCREEN_HEIGHT / h)
    if scale == 1.0:
        return surface
    return pygame.transform.smoothscale(surface, (max(1, int(w * scale)), max(1, int(h * scale))))


def _extract_date(path: str) -> str:
    """Return the file's mtime formatted as M/D/YYYY, or '' on error."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%-m/%-d/%Y")
    except OSError:
        return ""


def _extract_number(path: str) -> str:
    """Return the numeric portion of a filename like 000042.jpg as '42', or ''."""
    name = os.path.splitext(os.path.basename(path))[0]
    return str(int(name)) if name.isdigit() else ""


class PhotoProvider:
    def __init__(self):
        self._files: list[str] = []
        self._files_scanned = 0.0          # monotonic of last scan
        self._shuffle: list[str] = []      # remaining paths in current shuffle deck
        self._ready: tuple | None = None   # pre-decoded (surface, date, number)
        self._lock = threading.Lock()
        self._want = threading.Event()     # signals background to decode next photo
        self._want.set()

    # -- public API (main thread) ------------------------------------------
    def next_surface(self) -> tuple[pygame.Surface, str, str] | None:
        """Return the pre-decoded (surface, date, number) and trigger the next decode."""
        with self._lock:
            result = self._ready
            self._ready = None
        self._want.set()
        return result

    # -- background loop ---------------------------------------------------
    def run(self):
        while True:
            try:
                self._tick()
            except Exception as e:
                logger.warning(f"photo provider error: {e}; retrying in {ERROR_BACKOFF}s")
                time.sleep(ERROR_BACKOFF)

    def _tick(self):
        self._want.wait()

        now = time.monotonic()
        if not self._files or (now - self._files_scanned) >= PHOTO_RESCAN_MINUTES * 60:
            self._scan()

        if not self._files:
            time.sleep(ERROR_BACKOFF)
            return

        self._want.clear()

        # Refill shuffle deck when exhausted — guarantees no repeats within a pass
        if not self._shuffle:
            self._shuffle = self._files.copy()
            random.shuffle(self._shuffle)
            logger.info(f"photo deck refilled: {len(self._shuffle)} photos")

        # Try a few candidates so one bad file doesn't stall the rotation
        for _ in range(10):
            if not self._shuffle:
                break
            path = self._shuffle.pop()
            try:
                surface = _fit(pygame.image.load(path))
            except (pygame.error, OSError) as e:
                logger.warning(f"skipping {path}: {e}")
                continue
            with self._lock:
                self._ready = (surface, _extract_date(path), _extract_number(path))
            return

        # All candidates failed; signal again so we retry immediately
        self._want.set()

    def _scan(self):
        if not os.path.isdir(PHOTO_DIR):
            logger.warning(f"photo dir not available: {PHOTO_DIR}")
            self._files = []
            return
        files = []
        for root, _dirs, names in os.walk(PHOTO_DIR):
            for name in names:
                if name.lower().endswith(IMAGE_EXTS):
                    files.append(os.path.join(root, name))
        random.shuffle(files)
        self._files = files
        self._files_scanned = time.monotonic()
        # Invalidate the current deck so we pick up any new/removed files
        self._shuffle = []
        logger.info(f"scanned {len(files)} photos in {PHOTO_DIR}")
