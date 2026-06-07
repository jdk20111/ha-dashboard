# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A fullscreen pygame dashboard for a Raspberry Pi that displays live Home Assistant sensor data. It renders to `/dev/fb0` directly (bypassing X11/Wayland), managed by a systemd service.

## Dependencies

```bash
pip install pygame numpy websockets
```

## Configuration

`config.py` reads `HA_HOST`, `HA_PORT`, and `HA_TOKEN` from environment variables, falling back to defaults. `HA_WS_URL`, `SCREEN_WIDTH` (1024), and `SCREEN_HEIGHT` (600) are derived there. The service loads secrets via `EnvironmentFile=/home/jdk201/ha-dashboard/.env` (git-ignored); set `HA_TOKEN=...` in that file. To point at a different HA instance, edit the env var defaults in `config.py` or override in `.env`.

## Running and managing the service

```bash
# Run directly (renders to /dev/fb0 — must have write access)
python3 main.py

# Service management
sudo systemctl start ha-dashboard
sudo systemctl stop ha-dashboard
sudo systemctl restart ha-dashboard
sudo systemctl status ha-dashboard
journalctl -u ha-dashboard -f   # live logs

# Install or update service file
sudo cp ha-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## Architecture

The app has two threads:

1. **WebSocket thread** (`ws_thread` → `HAClient.run`): Connects to HA at `HA_WS_URL`, fetches a full state snapshot on connect, then subscribes to `state_changed` events. On each event, it merges the new state into `self.states` and calls `on_state_change(self.states)` — passing the **full** states dict every time, not a diff. `on_state_change` in `main.py` replaces `_states` under `_states_lock` and sets `_connected = True`. Reconnects automatically on failure with a 5-second backoff.

2. **Pygame main loop** (`main`): Runs at 10 FPS. Reads `_connected` under the lock each frame and renders all cards. If `_connected` is False, shows a connecting splash.

**Forecast data** flows via a separate `on_forecast` callback and `_forecast_lock`. `HAClient` requests forecast on connect (via `call_service weather.get_forecasts`) and re-requests whenever `weather.forecast_home` changes. Message IDs 1 and 2 are reserved for the handshake/subscription; dynamic requests start at 3.

## Display path

`SDL_VIDEODRIVER=offscreen` is set in `main.py` and the service file — pygame renders into an in-memory surface, never touching a real display. After each frame, `_write_to_fb()` converts the surface to raw RGB565 bytes via numpy and writes directly to `/dev/fb0` (the `vc4drmfb` framebuffer backed by the KMS/DRM pipeline). `pygame.display.flip()` is not called.

**Why not kmsdrm**: the `vc4drmfb` kernel driver holds DRM master permanently (the `vc4.kms_fbdev=0` parameter is silently ignored on this kernel — `vc4: unknown parameter 'kms_fbdev' ignored`), so SDL's kmsdrm driver can never acquire DRM master. Direct `/dev/fb0` file I/O is the working path.

**Restoring the console**: when the service is stopped, the last rendered frame stays frozen on screen. To restore the Linux console run: `sudo python3 -c "import fcntl,os; fd=os.open('/dev/tty1',os.O_RDWR); fcntl.ioctl(fd,0x4B3A,0); os.close(fd)"`

## Layout system

The screen is divided into a fixed header (`HDR_H = 90px`) and a 2-column × 3-row card grid. `card_rect(col, row)` returns the `pygame.Rect` for any card position. Card rendering functions (`draw_climate`, `draw_power`, etc.) each receive the surface, font dict, and rect, and are called from `main()` with explicit `card_rect` positions.

**Adding a new card**: write a `draw_*` function, then call it from `main()` with a `card_rect(col, row)` position. Use `draw_card()` to render the card background/header, then lay out content with the `row()` helper:

```python
def row(surf, fonts, x, y, label, value, val_color=TEXT, label_w=160) -> int:
    # renders label in DIM at x, value in val_color at x+label_w; returns y + LINE_H (28px)
```

**Font sizes** (Ubuntu/sans): `xl`=52 bold, `lg`=34 bold, `md`=22, `sm`=17.
