import time
import threading
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

class MinifierFileWatcher(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.target_file = None
        self.observer = None
        self._lock = threading.RLock()
        self._last_trigger = 0

    def start_watching(self, file_path: str | Path):
        if not HAS_WATCHDOG:
            return
            
        with self._lock:
            self.stop_watching()
            self.target_file = Path(file_path).resolve()
            
            if not self.target_file.exists():
                return
                
            self.observer = Observer()
            # Watch the directory containing the file
            self.observer.schedule(self, str(self.target_file.parent), recursive=False)
            self.observer.start()

    def stop_watching(self):
        with self._lock:
            if self.observer:
                self.observer.stop()
                self.observer.join()
                self.observer = None
            self.target_file = None

    def on_modified(self, event):
        if event.is_directory or not self.target_file:
            return
            
        try:
            modified_path = Path(event.src_path).resolve()
            if modified_path == self.target_file:
                # Debounce: prevent multiple triggers for a single save
                now = time.time()
                if now - self._last_trigger > 0.3:
                    self._last_trigger = now
                    # Fire callback in a new thread to avoid blocking watchdog
                    threading.Thread(target=self.callback, daemon=True).start()
        except Exception:
            pass
