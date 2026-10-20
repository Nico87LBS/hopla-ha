"""Keep Home Assistant in step with Hopla through the server's live event stream."""
import asyncio
import logging

import aiohttp

from .sse import SSEParser, reconnect_delay, needs_refresh, completion_details, EVENT_CONNECTED

_LOGGER = logging.getLogger(__name__)

SSE_PATH = "/api/v1/realtime/sse"
# The server sends a heartbeat every minute; three missed ones mean the link is gone.
READ_TIMEOUT = 180


class RealtimeListener:
    """Hold one stream open, refresh on every change and reconnect when it drops."""

    def __init__(self, session, base_url, token, on_change, on_status, on_completed=None):
        self._session = session
        self._url = base_url.rstrip("/") + SSE_PATH
        self._token = token
        self._on_change = on_change
        self._on_status = on_status
        self._on_completed = on_completed
        self.connected = False

    async def run(self):
        """Listen until cancelled."""
        attempt = 0
        while True:
            try:
                await self._listen()
                attempt = 0
            except asyncio.CancelledError:
                self._set_connected(False)
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                _LOGGER.debug("Hopla live updates interrupted: %s", err)
            self._set_connected(False)
            delay = reconnect_delay(attempt)
            attempt += 1
            await asyncio.sleep(delay)

    async def _listen(self):
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=READ_TIMEOUT)
        headers = {"secretkey": self._token, "Accept": "text/event-stream"}
        async with self._session.get(self._url, headers=headers, timeout=timeout) as response:
            if response.status == 503:
                raise ValueError("live updates are turned off on the Hopla server")
            response.raise_for_status()
            parser = SSEParser()
            async for raw in response.content:
                event = parser.feed_line(raw.decode("utf-8", errors="replace"))
                if event is None:
                    continue
                if event.get("type") == EVENT_CONNECTED:
                    # Catch up on whatever changed while disconnected.
                    self._set_connected(True)
                if self._on_completed is not None and (details := completion_details(event)):
                    self._on_completed(details)
                if needs_refresh(event):
                    await self._on_change()

    def _set_connected(self, connected):
        if connected != self.connected:
            self.connected = connected
            _LOGGER.info("Hopla live updates %s", "connected" if connected else "disconnected")
            self._on_status(connected)
