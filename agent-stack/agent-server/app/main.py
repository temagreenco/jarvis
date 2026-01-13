import os
import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException

from .schemas import RunRequest, RunStatus
from .graph import build_graph
from .tools import ensure_workspace, list_files

app = FastAPI(title="Agent Orchestration Server", version="1.0.0")

graph = build_graph()

# Use local data dir if /data doesn't exist (non-Docker mode)
DATA_DIR = os.getenv("DATA_DIR", "/data")
if not Path(DATA_DIR).exists():
    DATA_DIR = str(Path(__file__).parent.parent.parent / "data")
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
runs: dict[str, RunStatus] = {}


@app.get("/health")
def health():
    return {"ok": True}


async def run_graph(run_id: str, task: str):
    try:
        ws = ensure_workspace(DATA_DIR, run_id)
        runs[run_id].status = "running"
        runs[run_id].workspace = ws

        state = {
            "run_id": run_id,
            "task": task,
            "workspace": ws,
            "messages": [],
            "steps": 0,
            "done": False,
        }

        # Run synchronously in thread pool to not block
        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, graph.invoke, state)

        runs[run_id].plan = out.get("plan")
        runs[run_id].steps = out.get("steps", 0)

        if out.get("error"):
            runs[run_id].status = "error"
            runs[run_id].error = out["error"]
        else:
            runs[run_id].status = "done"
            runs[run_id].result = out.get("final", "")

        runs[run_id].meta = {"files": list_files(ws)}
    except Exception as e:
        runs[run_id].status = "error"
        runs[run_id].error = str(e)


@app.post("/runs", response_model=RunStatus)
async def create_run(req: RunRequest):
    run_id = uuid.uuid4().hex[:12]
    runs[run_id] = RunStatus(run_id=run_id, status="queued", steps=0, meta={})
    asyncio.create_task(run_graph(run_id, req.task))
    return runs[run_id]


@app.get("/runs/{run_id}", response_model=RunStatus)
def get_run(run_id: str):
    if run_id not in runs:
        raise HTTPException(status_code=404, detail="run_id not found")
    return runs[run_id]


@app.get("/runs")
def list_runs():
    return list(runs.values())
