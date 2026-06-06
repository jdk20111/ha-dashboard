import os

HA_HOST = os.environ.get("HA_HOST", "192.168.68.151")
HA_PORT = int(os.environ.get("HA_PORT", 8123))
HA_TOKEN = os.environ.get("HA_TOKEN", "")

HA_WS_URL = f"ws://{HA_HOST}:{HA_PORT}/api/websocket"

SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600
