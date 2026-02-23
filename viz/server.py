import asyncio
import json
from collections import deque
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from typing import List
import uvicorn
import threading
import os
from core.logger import logger

# Global state shared with the main orchestrator thread
class VizState:
    # N-2 (R2): explicit type annotations for IDE support and type-checker safety
    active_agent: str = "Idle"
    current_task: str = "Waiting..."
    # A-4: deque with maxlen=50 gives O(1) rotation vs list.pop(0) which is O(n)
    messages: deque[str] = deque(maxlen=50)
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def update(cls, agent, task, message=None):
        with cls._lock:
            cls.active_agent = agent
            cls.current_task = task
            if message:
                cls.messages.append(message)  # deque auto-drops oldest when full

    @classmethod
    def get_snapshot(cls):
        with cls._lock:
            return {
                "agent": cls.active_agent,
                "task": cls.current_task,
                "logs": list(cls.messages)[-5:]
            }

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # A-3: Collect dead connections without stopping mid-loop on a failure
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for c in dead:
            self.active_connections.remove(c)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send current state every 100ms
            data = VizState.get_snapshot()
            await websocket.send_text(json.dumps(data))
            await asyncio.sleep(0.1)
    except Exception:
        manager.disconnect(websocket)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

def start_server():
    logger.info("Starting Visualizer Server on http://127.0.0.1:8000")
    # C-5: Bind to 127.0.0.1 only — prevents exposing internal state to the network
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

def run_in_thread() -> threading.Thread:
    """Start the viz server in a daemon thread and return it (A-3 R2: caller can check .is_alive())."""
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    return t
