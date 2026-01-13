from pydantic import BaseModel
from typing import Optional, Dict, Any, List


class RunRequest(BaseModel):
    task: str


class RunStatus(BaseModel):
    run_id: str
    status: str  # queued|running|done|error
    result: Optional[str] = None
    plan: Optional[List[str]] = None
    steps: int = 0
    workspace: Optional[str] = None
    error: Optional[str] = None
    meta: Dict[str, Any] = {}
