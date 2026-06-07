import asyncio
import json
import websockets
import logging

logger = logging.getLogger(__name__)

WEATHER_ENTITY = "weather.pirateweather"


class HAClient:
    def __init__(self, url, token, on_state_change, on_forecast=None):
        self.url = url
        self.token = token
        self.on_state_change = on_state_change
        self.on_forecast = on_forecast
        self.states = {}
        self._msg_id = 3  # 1 and 2 are used during init
        self._forecast_id = None

    async def _request_forecast(self, ws):
        mid = self._msg_id
        self._msg_id += 1
        self._forecast_id = mid
        await ws.send(json.dumps({
            "id": mid,
            "type": "call_service",
            "domain": "weather",
            "service": "get_forecasts",
            "target": {"entity_id": WEATHER_ENTITY},
            "service_data": {"type": "daily"},
            "return_response": True,
        }))

    async def run(self):
        while True:
            try:
                await self._connect()
            except Exception as e:
                logger.warning(f"Connection lost: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _connect(self):
        async with websockets.connect(self.url) as ws:
            await ws.recv()  # auth_required
            await ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            auth_result = json.loads(await ws.recv())
            if auth_result.get("type") != "auth_ok":
                raise RuntimeError(f"Auth failed: {auth_result}")

            # Fetch current state snapshot
            await ws.send(json.dumps({"id": 1, "type": "get_states"}))
            result = json.loads(await ws.recv())
            for state in result.get("result", []):
                self.states[state["entity_id"]] = state
            self.on_state_change(self.states, None)

            # Subscribe to all state_changed events
            await ws.send(json.dumps({
                "id": 2,
                "type": "subscribe_events",
                "event_type": "state_changed",
            }))

            if self.on_forecast:
                await self._request_forecast(ws)

            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "event":
                    new = msg["event"]["data"].get("new_state")
                    if new:
                        entity_id = new["entity_id"]
                        self.states[entity_id] = new
                        self.on_state_change(self.states, entity_id)
                        # Refresh forecast when the weather entity updates
                        if self.on_forecast and new["entity_id"] == WEATHER_ENTITY:
                            await self._request_forecast(ws)
                elif msg.get("type") == "result" and msg.get("id") == self._forecast_id:
                    if self.on_forecast and msg.get("success"):
                        try:
                            forecast = msg["result"]["response"][WEATHER_ENTITY]["forecast"]
                            self.on_forecast(forecast)
                        except (KeyError, TypeError):
                            pass
