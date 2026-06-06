import asyncio
import os
import threading
import time
import numpy as np
import pygame
from config import HA_WS_URL, HA_TOKEN, SCREEN_WIDTH, SCREEN_HEIGHT
from ha_client import HAClient

os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
_states: dict = {}
_states_lock = threading.Lock()
_connected = False


def on_state_change(new_states: dict):
    global _states, _connected
    with _states_lock:
        _states = new_states
        _connected = True


def ws_thread():
    client = HAClient(HA_WS_URL, HA_TOKEN, on_state_change)
    asyncio.run(client.run())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _s(entity_id: str) -> dict | None:
    return _states.get(entity_id)


def state_of(entity_id: str, default: str = "--") -> str:
    s = _s(entity_id)
    return s["state"] if s else default


def attr_of(entity_id: str, attr: str, default=None):
    s = _s(entity_id)
    return s["attributes"].get(attr, default) if s else default


def fmt_temp(val) -> str:
    try:
        return f"{float(val):.0f}°F"
    except (TypeError, ValueError):
        return str(val) if val else "--"


def fmt_power() -> str:
    try:
        w = float(state_of("sensor.xcel_itron_instantaneous_demand_value", "0"))
        return f"{w / 1000:.2f} kW" if w >= 1000 else f"{w:.0f} W"
    except (TypeError, ValueError):
        return "--"


def fmt_speed(entity_id: str) -> str:
    try:
        val = float(state_of(entity_id, "0"))
        return f"{val / 1024:.1f} MiB/s" if val >= 1024 else f"{val:.0f} KiB/s"
    except (TypeError, ValueError):
        return "--"


WEATHER_LABELS = {
    "sunny": "Sunny", "clear-night": "Clear", "partlycloudy": "Partly Cloudy",
    "cloudy": "Cloudy", "fog": "Foggy", "hail": "Hail",
    "lightning": "Lightning", "lightning-rainy": "T-Storm",
    "pouring": "Pouring", "rainy": "Rainy", "snowy": "Snowy",
    "snowy-rainy": "Sleet", "windy": "Windy", "windy-variant": "Gusty",
}

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
BG        = (12,  15,  25)
CARD_BG   = (22,  28,  48)
CARD_HEAD = (32,  42,  72)
TEXT      = (210, 218, 235)
DIM       = (100, 112, 148)
ACCENT    = (70,  150, 255)
GREEN     = (75,  200, 110)
ORANGE    = (255, 160,  40)
RED       = (240,  80,  70)
YELLOW    = (240, 200,  50)

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
PAD      = 12
HDR_H    = 90
CARD_W   = (SCREEN_WIDTH  - PAD * 3) // 2   # 2 columns
CARD_H   = (SCREEN_HEIGHT - HDR_H - PAD * 4) // 3  # 3 rows
TITLE_H  = 26
LINE_H   = 28


def card_rect(col: int, row: int) -> pygame.Rect:
    x = PAD + col * (CARD_W + PAD)
    y = HDR_H + PAD + row * (CARD_H + PAD)
    return pygame.Rect(x, y, CARD_W, CARD_H)


def draw_card(surf: pygame.Surface, fonts: dict, rect: pygame.Rect, title: str):
    pygame.draw.rect(surf, CARD_BG, rect, border_radius=8)
    head = pygame.Rect(rect.x, rect.y, rect.w, TITLE_H)
    pygame.draw.rect(surf, CARD_HEAD, head,
                     border_top_left_radius=8, border_top_right_radius=8)
    surf.blit(fonts["sm"].render(title, True, ACCENT), (rect.x + 10, rect.y + 5))


def row(surf, fonts, x, y, label, value, val_color=TEXT, label_w=160):
    surf.blit(fonts["sm"].render(label, True, DIM), (x, y + 4))
    surf.blit(fonts["md"].render(str(value), True, val_color), (x + label_w, y))
    return y + LINE_H


# ---------------------------------------------------------------------------
# Card renderers
# ---------------------------------------------------------------------------
def draw_header(surf: pygame.Surface, fonts: dict):
    now = time.localtime()
    clock_str = time.strftime("%-I:%M %p", now)
    date_str  = time.strftime("%A, %B %-d", now)

    surf.blit(fonts["xl"].render(clock_str, True, TEXT), (PAD + 4, 8))
    surf.blit(fonts["sm"].render(date_str,  True, DIM),  (PAD + 6, 62))

    # Weather block on right
    wx_state = state_of("weather.forecast_home", "")
    wx_label = WEATHER_LABELS.get(wx_state, wx_state.replace("-", " ").title())
    wx_temp  = attr_of("weather.forecast_home", "temperature")
    wx_hum   = attr_of("weather.forecast_home", "humidity")
    wx_wind  = attr_of("weather.forecast_home", "wind_speed")

    parts = [wx_label]
    if wx_temp is not None:
        parts.append(fmt_temp(wx_temp))
    if wx_hum is not None:
        parts.append(f"Hum {wx_hum}%")
    if wx_wind is not None:
        parts.append(f"Wind {wx_wind:.0f} mph")

    wx_line1 = f"{parts[0]}  {parts[1]}" if len(parts) >= 2 else parts[0]
    wx_line2 = "  ".join(parts[2:]) if len(parts) > 2 else ""

    s1 = fonts["lg"].render(wx_line1, True, TEXT)
    surf.blit(s1, (SCREEN_WIDTH - s1.get_width() - PAD, 10))
    if wx_line2:
        s2 = fonts["sm"].render(wx_line2, True, DIM)
        surf.blit(s2, (SCREEN_WIDTH - s2.get_width() - PAD, 50))

    pygame.draw.line(surf, CARD_HEAD, (0, HDR_H - 1), (SCREEN_WIDTH, HDR_H - 1))


def draw_climate(surf, fonts, rect):
    draw_card(surf, fonts, rect, "CLIMATE")
    x, y = rect.x + 10, rect.y + TITLE_H + 6

    up_temp = state_of("sensor.ecobee_upstairs_current_temperature")
    dn_temp = state_of("sensor.downstairs_temperature")
    hum     = state_of("sensor.ecobee_upstairs_current_humidity")
    t_state = state_of("climate.ecobee_thermostat_thermostat")
    t_act   = attr_of("climate.ecobee_thermostat_thermostat", "hvac_action", "")
    t_lo    = attr_of("climate.ecobee_thermostat_thermostat", "target_temp_low")
    t_hi    = attr_of("climate.ecobee_thermostat_thermostat", "target_temp_high")

    y = row(surf, fonts, x, y, "Upstairs",   fmt_temp(up_temp))
    y = row(surf, fonts, x, y, "Downstairs", fmt_temp(dn_temp))
    y = row(surf, fonts, x, y, "Humidity",   f"{hum}%")

    tstat_val = t_state.replace("_", " ").title()
    if t_act:
        tstat_val += f" • {t_act}"
    if t_lo and t_hi:
        tstat_val += f"  ({t_lo}–{t_hi}°F)"
    y = row(surf, fonts, x, y, "Thermostat", tstat_val, DIM)


def draw_power(surf, fonts, rect):
    draw_card(surf, fonts, rect, "POWER & NETWORK")
    x, y = rect.x + 10, rect.y + TITLE_H + 4

    pw = fmt_power()
    pw_surf = fonts["lg"].render(pw, True, YELLOW)
    surf.blit(pw_surf, (rect.x + rect.w // 2 - pw_surf.get_width() // 2, y))
    y += 40

    dl = fmt_speed("sensor.m5_download_speed")
    ul = fmt_speed("sensor.m5_upload_speed")
    clients = state_of("sensor.tp_link_router_total_clients")

    y = row(surf, fonts, x, y, "Download", dl, GREEN)
    y = row(surf, fonts, x, y, "Upload",   ul, ACCENT)
    row(surf, fonts, x, y, "Devices", f"{clients} connected", DIM)


def draw_security(surf, fonts, rect):
    draw_card(surf, fonts, rect, "SECURITY & HOME")
    x, y = rect.x + 10, rect.y + TITLE_H + 6

    garage = state_of("cover.garage_door")
    g_color = GREEN if garage == "closed" else ORANGE
    y = row(surf, fonts, x, y, "Garage Door",
            garage.upper() if garage != "--" else "--", g_color)

    water = state_of("sensor.water_tank_level")
    y = row(surf, fonts, x, y, "Water Tank", water)

    ht_temp = attr_of("climate.hottub", "current_temperature")
    ht_set  = attr_of("climate.hottub", "temperature")
    ht_act  = attr_of("climate.hottub", "hvac_action", "")
    ht_val  = fmt_temp(ht_temp)
    if ht_set:
        ht_val += f"  (set {fmt_temp(ht_set)})"
    if ht_act and ht_act != "off":
        ht_val += f"  ▲ heating"
    y = row(surf, fonts, x, y, "Hot Tub", ht_val)

    vacuum = state_of("sensor.dusty_rhodes_station_state")
    row(surf, fonts, x, y, "Dusty Rhodes", vacuum.title())


def draw_printer(surf, fonts, rect):
    draw_card(surf, fonts, rect, "3D PRINTER")
    x, y = rect.x + 10, rect.y + TITLE_H + 6

    status   = state_of("sensor.p1s_01p00c511600214_print_status")
    progress = state_of("sensor.p1s_01p00c511600214_print_progress")
    online   = state_of("binary_sensor.p1s_01p00c511600214_online")

    o_color = GREEN if online == "on" else RED
    y = row(surf, fonts, x, y, "Bambu P1S",
            "Online" if online == "on" else "Offline", o_color)

    s_color = ACCENT if status not in ("idle", "--", "unavailable") else DIM
    y = row(surf, fonts, x, y, "Status", status.title(), s_color)

    if status not in ("idle", "unavailable", "--"):
        try:
            pct = float(progress)
            bar_w = rect.w - 24
            bar_rect = pygame.Rect(x, y, bar_w, 14)
            pygame.draw.rect(surf, CARD_HEAD, bar_rect, border_radius=4)
            fill_w = int(bar_w * pct / 100)
            if fill_w > 0:
                pygame.draw.rect(surf, ACCENT,
                                 pygame.Rect(x, y, fill_w, 14), border_radius=4)
            y += 20
            row(surf, fonts, x, y, "Progress", f"{pct:.0f}%", ACCENT)
        except (TypeError, ValueError):
            row(surf, fonts, x, y, "Progress", str(progress))
    else:
        row(surf, fonts, x, y, "Progress", "--", DIM)


def draw_calendar(surf, fonts, rect):
    draw_card(surf, fonts, rect, "UPCOMING EVENTS")
    x, y = rect.x + 10, rect.y + TITLE_H + 6

    raw = state_of("sensor.upcoming_calendar_events", "")
    events = [e.strip() for e in raw.split("|") if e.strip()] if raw and raw != "--" else []

    if not events:
        surf.blit(fonts["sm"].render("No upcoming events", True, DIM), (x, y + 6))
        return

    max_w = rect.w - 20
    for ev in events[:4]:
        s = fonts["sm"].render(ev, True, TEXT)
        if s.get_width() > max_w:
            # Truncate with ellipsis
            while s.get_width() > max_w and len(ev) > 3:
                ev = ev[:-1]
                s = fonts["sm"].render(ev + "...", True, TEXT)
            s = fonts["sm"].render(ev + "...", True, TEXT)
        surf.blit(s, (x, y))
        y += 22
        if y > rect.bottom - 10:
            break


def draw_lights(surf, fonts, rect):
    draw_card(surf, fonts, rect, "LIGHTS & SWITCHES")
    x, y = rect.x + 10, rect.y + TITLE_H + 6

    lights = [
        ("Porch",       "light.porch_light"),
        ("Landscape",   "light.landscape_lights"),
        ("Kitchen Bar", "light.kitchen_bar_lights"),
        ("Kitchen Ctr", "light.kitchen_counter_lights"),
        ("Shop",        "light.shop_lights"),
        ("Garage",      "light.garage_light_center"),
    ]

    col2_x = rect.x + rect.w // 2
    for i, (label, eid) in enumerate(lights):
        lx = x if i % 2 == 0 else col2_x
        ly = y + (i // 2) * LINE_H
        st = state_of(eid)
        color = GREEN if st == "on" else DIM
        dot = fonts["md"].render("●", True, color)
        surf.blit(dot, (lx, ly))
        surf.blit(fonts["sm"].render(label, True, TEXT if st == "on" else DIM),
                  (lx + 18, ly + 4))


_fb_file = None

def _open_fb():
    global _fb_file
    try:
        _fb_file = open("/dev/fb0", "r+b")
    except OSError as e:
        print(f"Warning: cannot open /dev/fb0: {e}", flush=True)

def _write_to_fb(surface: pygame.Surface):
    if _fb_file is None:
        return
    px = pygame.surfarray.array3d(surface)   # (W, H, 3) uint8, RGB
    px = px.transpose(1, 0, 2)              # (H, W, 3)
    r = px[:, :, 0].astype(np.uint16)
    g = px[:, :, 1].astype(np.uint16)
    b = px[:, :, 2].astype(np.uint16)
    rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    _fb_file.seek(0)
    _fb_file.write(rgb565.tobytes())
    _fb_file.flush()


def draw_connecting(surf, fonts):
    msg = "Connecting to Home Assistant..."
    s = fonts["md"].render(msg, True, ORANGE)
    surf.blit(s, (SCREEN_WIDTH // 2 - s.get_width() // 2,
                  SCREEN_HEIGHT // 2 - s.get_height() // 2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    _open_fb()
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.mouse.set_visible(False)

    fonts = {
        "xl": pygame.font.SysFont("ubuntu,sans", 52, bold=True),
        "lg": pygame.font.SysFont("ubuntu,sans", 34, bold=True),
        "md": pygame.font.SysFont("ubuntu,sans", 22),
        "sm": pygame.font.SysFont("ubuntu,sans", 17),
    }

    threading.Thread(target=ws_thread, daemon=True).start()
    clock = pygame.time.Clock()

    while True:
        screen.fill(BG)

        with _states_lock:
            connected = _connected

        if not connected:
            draw_connecting(screen, fonts)
        else:
            draw_header(screen, fonts)
            draw_climate(screen,  fonts, card_rect(0, 0))
            draw_power(screen,    fonts, card_rect(1, 0))
            draw_security(screen, fonts, card_rect(0, 1))
            draw_printer(screen,  fonts, card_rect(1, 1))
            draw_calendar(screen, fonts, card_rect(0, 2))
            draw_lights(screen,   fonts, card_rect(1, 2))

        _write_to_fb(screen)
        clock.tick(10)

    pygame.quit()


if __name__ == "__main__":
    main()
