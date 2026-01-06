"""
JARVIS HTTP API - Remote access to JARVIS capabilities

Features:
- POST /process - Submit video processing job
- GET /status - Get system status
- GET /jobs/{job_id} - Get job status
- WebSocket /ws/jobs/{job_id} - Real-time job updates

Run with: uvicorn api:app --host 0.0.0.0 --port 8000
"""
import asyncio
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.jarvis import get_jarvis
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("api")


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobCreate(BaseModel):
    """Request body for creating a processing job."""
    video_url: Optional[str] = Field(None, description="URL to download video from")
    video_path: Optional[str] = Field(None, description="Local path to video file")
    num_reels: int = Field(default=8, ge=1, le=20, description="Number of reels to generate")
    output_dir: Optional[str] = Field(None, description="Output directory path")

    model_config = {"json_schema_extra": {
        "example": {
            "video_path": "/videos/podcast.mp4",
            "num_reels": 5,
        }
    }}


class JobResponse(BaseModel):
    """Response for job operations."""
    job_id: str
    status: JobStatus
    created_at: str
    completed_at: Optional[str] = None
    progress: int = Field(default=0, ge=0, le=100)
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class StatusResponse(BaseModel):
    """System status response."""
    version: str
    initialized: bool
    modules: list[dict[str, str]]
    memory_stats: dict[str, Any]
    active_jobs: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str


# In-memory job storage (production would use Redis/DB)
jobs: dict[str, JobResponse] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("JARVIS API starting up...")
    jarvis = get_jarvis()
    jarvis.initialize()
    logger.info("JARVIS initialized")
    yield
    logger.info("JARVIS API shutting down...")


app = FastAPI(
    title="JARVIS API",
    description="Autonomous AI System for viral content creation",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def process_video_task(job_id: str, video_path: str, num_reels: int, output_dir: str) -> None:
    """Background task to process video."""
    jobs[job_id].status = JobStatus.RUNNING
    jobs[job_id].progress = 10

    try:
        jarvis = get_jarvis()

        # Simulate progress updates (real impl would hook into pipeline)
        jobs[job_id].progress = 30

        result = jarvis.process(
            task="Create viral reels from video",
            video_path=video_path,
            output_dir=output_dir,
            num_reels=num_reels,
        )

        jobs[job_id].progress = 100
        jobs[job_id].completed_at = datetime.now().isoformat()

        if result.success:
            jobs[job_id].status = JobStatus.COMPLETED
            jobs[job_id].result = result.data
        else:
            jobs[job_id].status = JobStatus.FAILED
            jobs[job_id].error = result.error

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        jobs[job_id].status = JobStatus.FAILED
        jobs[job_id].error = str(e)
        jobs[job_id].completed_at = datetime.now().isoformat()


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Health check endpoint for load balancers."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
    )


@app.get("/status", response_model=StatusResponse, tags=["System"])
async def get_status() -> StatusResponse:
    """Get JARVIS system status."""
    jarvis = get_jarvis()
    status = jarvis.get_status()

    return StatusResponse(
        version="0.1.0",
        initialized=status["initialized"],
        modules=status["modules"],
        memory_stats=status["memory_stats"],
        active_jobs=sum(1 for j in jobs.values() if j.status == JobStatus.RUNNING),
    )


@app.post("/process", response_model=JobResponse, tags=["Jobs"])
async def create_job(
    job: JobCreate,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """
    Submit a video processing job.

    Either `video_url` or `video_path` must be provided.
    Returns immediately with a job_id for tracking.
    """
    if not job.video_path and not job.video_url:
        raise HTTPException(400, "Either video_path or video_url must be provided")

    video_path = job.video_path
    if job.video_url:
        # Download video from URL
        raise HTTPException(501, "URL download not yet implemented - use video_path")

    if video_path and not Path(video_path).exists():
        raise HTTPException(400, f"Video file not found: {video_path}")

    job_id = str(uuid.uuid4())[:8]
    output_dir = job.output_dir or str(settings.output_dir / job_id)

    job_response = JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        created_at=datetime.now().isoformat(),
        progress=0,
    )
    jobs[job_id] = job_response

    background_tasks.add_task(
        process_video_task,
        job_id,
        video_path,
        job.num_reels,
        output_dir,
    )

    logger.info(f"Created job {job_id} for video: {video_path}")
    return job_response


@app.post("/upload", response_model=JobResponse, tags=["Jobs"])
async def upload_and_process(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Video file to process"),
    num_reels: int = Query(default=8, ge=1, le=20, description="Number of reels"),
) -> JobResponse:
    """
    Upload a video file and start processing.

    For large files, prefer using /process with a pre-uploaded file path.
    """
    if not file.filename:
        raise HTTPException(400, "No file provided")

    # Save uploaded file
    upload_dir = settings.videos_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())[:8]
    file_ext = Path(file.filename).suffix or ".mp4"
    video_path = upload_dir / f"{job_id}{file_ext}"

    try:
        content = await file.read()
        video_path.write_bytes(content)
        logger.info(f"Saved uploaded file: {video_path} ({len(content)} bytes)")
    except Exception as e:
        raise HTTPException(500, f"Failed to save file: {e}")

    output_dir = str(settings.output_dir / job_id)

    job_response = JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        created_at=datetime.now().isoformat(),
        progress=0,
    )
    jobs[job_id] = job_response

    background_tasks.add_task(
        process_video_task,
        job_id,
        str(video_path),
        num_reels,
        output_dir,
    )

    return job_response


@app.get("/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
async def get_job(job_id: str) -> JobResponse:
    """Get the status of a processing job."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job not found: {job_id}")
    return jobs[job_id]


@app.get("/jobs", response_model=list[JobResponse], tags=["Jobs"])
async def list_jobs(
    status: Optional[JobStatus] = Query(None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
) -> list[JobResponse]:
    """List all processing jobs."""
    result = list(jobs.values())

    if status:
        result = [j for j in result if j.status == status]

    return sorted(result, key=lambda j: j.created_at, reverse=True)[:limit]


@app.delete("/jobs/{job_id}", tags=["Jobs"])
async def delete_job(job_id: str) -> dict[str, str]:
    """Delete a completed or failed job."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job not found: {job_id}")

    job = jobs[job_id]
    if job.status == JobStatus.RUNNING:
        raise HTTPException(400, "Cannot delete a running job")

    del jobs[job_id]
    return {"message": f"Job {job_id} deleted"}


@app.get("/download/{job_id}/{filename}", tags=["Files"])
async def download_file(job_id: str, filename: str) -> FileResponse:
    """Download a generated reel file."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job not found: {job_id}")

    job = jobs[job_id]
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(400, "Job not completed")

    file_path = settings.output_dir / job_id / filename
    if not file_path.exists():
        raise HTTPException(404, f"File not found: {filename}")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="video/mp4",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
