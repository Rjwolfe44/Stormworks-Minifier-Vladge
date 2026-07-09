import time
import threading
import logging

try:
    from pypresence import Presence
    HAS_PYPRESENCE = True
except ImportError:
    HAS_PYPRESENCE = False

# Default client ID; customizable for custom registered Discord applications.
# Requires a registered application on the Discord Developer Portal for images to display.
CLIENT_ID = "1140000000000000000"  

class DiscordRPC:
    def __init__(self, client_id=CLIENT_ID):
        self.client_id = client_id
        self.rpc = None
        self.connected = False
        self.thread = None
        self._state = "Idling"
        self._details = "Ready to optimize"
        self._start_time = int(time.time())
        self._stop_event = threading.Event()
        self._last_update = 0

    def connect(self):
        if not HAS_PYPRESENCE:
            return

        def _connect_loop():
            while not self._stop_event.is_set():
                try:
                    if not self.connected:
                        self.rpc = Presence(self.client_id)
                        self.rpc.connect()
                        self.connected = True
                        self._push_update()
                except Exception as e:
                    self.connected = False
                    # Fail silently if Discord is not running
                time.sleep(15)  # Retry/keepalive interval
                
        self.thread = threading.Thread(target=_connect_loop, daemon=True)
        self.thread.start()

    def update(self, state: str, details: str):
        self._state = state
        self._details = details
        self._push_update()

    def _push_update(self):
        if not self.connected or not self.rpc:
            return
            
        # Discord limits updates to roughly once per 15 seconds
        now = time.time()
        if now - self._last_update < 2:
            return
            
        try:
            self.rpc.update(
                state=self._state,
                details=self._details,
                start=self._start_time,
                large_text="VladgeMinifier"
            )
            self._last_update = time.time()
        except Exception:
            self.connected = False

    def close(self):
        self._stop_event.set()
        if self.connected and self.rpc:
            try:
                self.rpc.close()
            except Exception:
                pass
