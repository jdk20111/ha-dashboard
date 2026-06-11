"""Background photo provider for the dashboard slideshow.

Reads images from a local/network folder (PHOTO_DIR) — populate it however you
like (a network drive synced from Google Photos / iCloud, a Takeout export, a
manual copy). Runs on its own thread, mirroring ha_client.HAClient: it
periodically re-scans the folder and keeps a small cache of decoded,
panel-sized pygame surfaces in RAM. The main loop pulls a random cached surface
via next_surface(); if the folder is missing/empty (e.g. an unmounted network
share) it simply returns None and the dashboard keeps showing.
"""
import logging
import os
import random
import threading
import time
from collections import deque
from datetime import datetime

import pygame

from config import (
    PHOTO_DIR, PHOTO_RESCAN_MINUTES, PHOTO_CACHE_SIZE,
    SCREEN_WIDTH, SCREEN_HEIGHT,
)

logger = logging.getLogger(__name__)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
ERROR_BACKOFF = 30         # seconds to wait after a failed tick
ROTATE_INTERVAL = 30       # seconds between swapping in a fresh photo once full


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
        self._files_scanned = 0.0                      # monotonic of last scan
        self._cache: deque[tuple[pygame.Surface, str, str]] = deque(maxlen=PHOTO_CACHE_SIZE)
        self._queue: list[int] = []   # shuffled indices into _cache; refilled when exhausted
        self._lock = threading.Lock()

    # -- public API (main thread) ------------------------------------------
    def next_surface(self) -> tuple[pygame.Surface, str, str] | None:
        """Return the next (surface, date, number) from a shuffle deck; no repeats until all shown."""
        with self._lock:
            if not self._cache:
                return None
            snapshot = list(self._cache)
            if len(self._queue) != len(snapshot):
                # Cache grew or shrank — rebuild deck, keeping remaining unseen indices where valid
                self._queue = list(range(len(snapshot)))
                random.shuffle(self._queue)
            idx = self._queue.pop()
            return snapshot[idx]

    # -- background loop ---------------------------------------------------
    def run(self):
        while True:
            try:
                self._tick()
            except Exception as e:
                logger.warning(f"photo provider error: {e}; retrying in {ERROR_BACKOFF}s")
                time.sleep(ERROR_BACKOFF)
            else:
                time.sleep(ROTATE_INTERVAL)

    def _tick(self):
        now = time.monotonic()
        if not self._files or (now - self._files_scanned) >= PHOTO_RESCAN_MINUTES * 60:
            self._scan()
        if not self._files:
            return
        # Fill the cache fast on startup; afterwards swap in one fresh photo per
        # tick so the slideshow keeps rotating through the folder over time.
        with self._lock:
            have = len(self._cache)
        maxlen = self._cache.maxlen or 1
        to_load = (maxlen - have) if have < maxlen else 1
        for _ in range(to_load):
            self._load_one()

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
        self._files = files
        self._files_scanned = time.monotonic()
        logger.info(f"scanned {len(files)} photos in {PHOTO_DIR}")

    def _load_one(self):
        # Try a few random files so one unreadable/undecodable image (or a brief
        # network hiccup) doesn't stall the rotation.
        for _ in range(5):
            path = random.choice(self._files)
            try:
                surface = _fit(pygame.image.load(path))
            except (pygame.error, OSError) as e:
                logger.warning(f"skipping {path}: {e}")
                continue
            with self._lock:
                self._cache.append((surface, _extract_date(path), _extract_number(path)))
            return
