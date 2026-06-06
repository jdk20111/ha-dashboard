# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A fullscreen pygame dashboard for a Raspberry Pi that displays live Home Assistant sensor data. It renders to `/dev/fb0` directly (bypassing X11/Wayland), managed by a systemd service.

## Dependencies

```bash
pip install pygame numpy websockets
```

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

1. **WebSocket thread** (`ws_thread` → `HAClient.run`): Connects to HA at `HA_WS_URL` from `config.py`, fetches a full state snapshot on connect, then subscribes to `state_changed` events. On each event, it merges the new state into `self.states` and calls `on_state_change(self.states)` — passing the **full** states dict every time, not a diff. `on_state_change` in `main.py` replaces `_states` under `_states_lock` and sets `_connected = True`. Reconnects automatically on failure with a 5-second backoff.

2. **Pygame main loop** (`main`): Runs at 10 FPS. Reads `_connected` under the lock each frame and renders all cards. If `_connected` is False, shows a connecting splash.

## Display path

`SDL_VIDEODRIVER=offscreen` is set in `main.py` and the service file — pygame renders into an in-memory surface, never touching a real display. After each frame, `_write_to_fb()` converts the surface to raw RGB565 bytes via numpy and writes directly to `/dev/fb0` (the `vc4drmfb` framebuffer backed by the KMS/DRM pipeline). `pygame.display.flip()` is not called.

**Why not kmsdrm**: the `vc4drmfb` kernel driver holds DRM master permanently (the `vc4.kms_fbdev=0` parameter is silently ignored on this kernel — `vc4: unknown parameter 'kms_fbdev' ignored`), so SDL's kmsdrm driver can never acquire DRM master. Direct `/dev/fb0` file I/O is the working path.

**Restoring the console**: when the service is stopped, the last rendered frame stays frozen on screen. To restore the Linux console run: `sudo python3 -c "import fcntl,os; fd=os.open('/dev/tty1',os.O_RDWR); fcntl.ioctl(fd,0x4B3A,0); os.close(fd)"`

## Configuration

`config.py` holds `HA_HOST`, `HA_PORT`, `HA_TOKEN`, `HA_WS_URL`, `SCREEN_WIDTH`, and `SCREEN_HEIGHT`. Edit this file to point at a different HA instance or change resolution.

## Layout system

The screen is divided into a fixed header (`HDR_H = 90px`) and a 2-column × 3-row card grid. `card_rect(col, row)` returns the `pygame.Rect` for any card position. Card rendering functions (`draw_climate`, `draw_power`, etc.) each receive the surface, font dict, and rect. Adding a new card means writing a `draw_*` function and calling it from `main()` with a `card_rect` position.
