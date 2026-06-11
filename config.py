import os

HA_HOST = os.environ.get("HA_HOST", "192.168.68.151")
HA_PORT = int(os.environ.get("HA_PORT", 8123))
HA_TOKEN = os.environ.get("HA_TOKEN", "")

HA_WS_URL = f"ws://{HA_HOST}:{HA_PORT}/api/websocket"

SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600

# ---------------------------------------------------------------------------
# Photo slideshow
# ---------------------------------------------------------------------------
# The dashboard alternates between the normal card view and a full-screen photo
# read from a local/network folder (PHOTO_DIR). Populate that folder however you
# like (e.g. a network drive synced from Google Photos, a Takeout export, or a
# manual copy). Disabled when PHOTO_DIR is unset, or via SLIDESHOW_ENABLED=0.
SLIDESHOW_ENABLED = os.environ.get("SLIDESHOW_ENABLED", "1") != "0"
SLIDESHOW_DASHBOARD_SECONDS = float(os.environ.get("SLIDESHOW_DASHBOARD_SECONDS", "20"))
SLIDESHOW_PHOTO_SECONDS = float(os.environ.get("SLIDESHOW_PHOTO_SECONDS", "20"))

# Directory to scan (recursively) for photos. May be a network mount.
PHOTO_DIR = os.environ.get("PHOTO_DIR", "")
# How often to re-scan PHOTO_DIR for added/removed files (minutes).
PHOTO_RESCAN_MINUTES = float(os.environ.get("PHOTO_RESCAN_MINUTES", "10"))
# Number of decoded photo surfaces to keep cached in RAM.
PHOTO_CACHE_SIZE = int(os.environ.get("PHOTO_CACHE_SIZE", "8"))

# True only when the slideshow is on AND a source directory is configured.
SLIDESHOW_ACTIVE = SLIDESHOW_ENABLED and bool(PHOTO_DIR)
