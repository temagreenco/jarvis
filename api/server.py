"""
Crispy API Server - FastAPI web service for script generation
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Any
from datetime import datetime
from uuid import uuid4
import os
import asyncio

from modules.script_generator import ScriptGeneratorModule, GeneratedScript
from modules.db_models import Job, db_session, init_db
from modules.job_queue import JobQueue
from modules.minio_client import presign_get_url, presign_put_url
from prompts.beauty_prompts import register_beauty_prompts
from utils.logger import get_logger

logger = get_logger("api")

# Initialize FastAPI
app = FastAPI(
    title="Crispy API",
    description="AI Script Generator for Beauty Professionals",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global generator instance
generator: Optional[ScriptGeneratorModule] = None
job_queue: Optional[JobQueue] = None


# =============================================================================
# Request/Response Models
# =============================================================================

class GenerateRequest(BaseModel):
    """Request for script generation"""
    niche: str = Field(default="general", description="Beauty niche: nails, hair, makeup, general")
    status: str = Field(default="practitioner", description="User status: practitioner, academy_owner")
    goal: str = Field(default="exposure", description="Content goal: exposure, value, sales")
    tone: str = Field(default="casual", description="Tone: professional, casual, energetic, slang")
    topic: Optional[str] = Field(default=None, description="Specific topic (e.g., 'Ч’Чњ Ч¦Ч™Ч¤Ч•ЧЁЧ Ч™Ч™Чќ')")
    num_scripts: int = Field(default=5, ge=1, le=10, description="Number of scripts (1-10)")
    provider: Optional[str] = Field(default=None, description="AI provider: openai, gemini, claude")

    class Config:
        json_schema_extra = {
            "example": {
                "niche": "nails",
                "status": "practitioner",
                "goal": "exposure",
                "tone": "slang",
                "topic": "Ч’Чњ Ч¦Ч™Ч¤Ч•ЧЁЧ Ч™Ч™Чќ",
                "num_scripts": 5,
                "provider": "openai"
            }
        }


class ScriptResponse(BaseModel):
    """Single script in response"""
    hook: str
    body: str
    cta: str
    hashtags: list[str] = []
    music_suggestion: str = ""
    duration_estimate: str = "15-30 seconds"


class GenerateResponse(BaseModel):
    """Response from script generation"""
    success: bool
    scripts: list[ScriptResponse]
    provider: str
    model: str
    tokens_used: int
    cost_usd: float


class RefineRequest(BaseModel):
    """Request to refine a script"""
    script: ScriptResponse
    feedback: str = Field(description="User feedback for refinement")
    provider: Optional[str] = None


class OptionsResponse(BaseModel):
    """Available generation options"""
    niches: list[str]
    statuses: list[str]
    goals: list[str]
    tones: list[str]
    providers: list[str]


class JobCreateRequest(BaseModel):
    """Request to create a processing job"""
    source_url: Optional[str] = Field(default=None, description="Input video URL")
    input_s3_key: Optional[str] = Field(
        default=None, description="Input MinIO key (preferred in production)"
    )
    task: Optional[str] = Field(default="cut", description="cut | auto_clips")
    auto_clips: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Auto clip params: {max_clips, min_duration, max_duration, min_sentences, "
            "max_sentences, hook_bias, score_threshold, min_avg_word_confidence, diversity_radius_s, "
            "language, target_duration_sec, prefer_duration_min_sec, prefer_duration_max_sec, "
            "max_duration_sec, enable_extend_to_completion, sentence_max_gap, extend_silence_gap_sec}"
        ),
    )
    transcript_s3_key: Optional[str] = Field(
        default=None, description="Optional MinIO key for transcript JSON"
    )
    transcript: Optional[dict[str, Any]] = Field(
        default=None, description="Optional inline transcript payload"
    )
    segments: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="List of segments to cut: [{id, start, end}]",
    )
    boundary_mode: Optional[str] = Field(
        default=None,
        description="Boundary mode: word | sentence | silence",
    )
    render_mode: Optional[str] = Field(
        default=None,
        description="Render mode: original | reels",
    )
    track_mode: Optional[str] = Field(
        default=None,
        description="Tracking mode: none | face",
    )
    reels: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Reels options: {target_w, target_h, sample_fps, smoothing, deadzone_px, max_pan_px_per_s}"
        ),
    )
    snap_to_silence: Optional[bool] = Field(default=None, description="Snap to silence")
    snap_window_sec: Optional[float] = Field(
        default=None, description="Silence snap window in seconds"
    )
    hook_first_cutting: Optional[bool] = Field(
        default=None, description="Shift clip start to earliest strong hook"
    )
    hook_window_sec: Optional[float] = Field(
        default=None, description="Hook search window in seconds"
    )
    hook_min_rms_db: Optional[float] = Field(
        default=None, description="Minimum RMS dB for hook start"
    )
    mode: Optional[str] = Field(default="accurate", description="fast | accurate")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary job metadata")

    @model_validator(mode="after")
    def validate_task(self) -> "JobCreateRequest":
        task = self.task or "cut"
        if task == "cut":
            if not self.segments:
                raise ValueError("segments is required for task='cut'")
        elif task == "auto_clips":
            pass
        else:
            raise ValueError("task must be 'cut' or 'auto_clips'")
        return self


class ClipLink(BaseModel):
    id: str
    url: str
    reels_url: Optional[str] = None


class JobLinks(BaseModel):
    output: Optional[str] = None
    clips: list[ClipLink] = []


class JobStatusResponse(BaseModel):
    id: str
    status: str
    links: JobLinks
    progress: Optional[float] = None
    progress_stage: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class UploadUrlRequest(BaseModel):
    filename: str = Field(description="Original filename")
    content_type: Optional[str] = Field(default=None, description="Optional content type")
    prefix: Optional[str] = Field(default="inputs", description="Key prefix (default: inputs)")


class UploadUrlResponse(BaseModel):
    key: str
    upload_url: str
    expires_seconds: int


# =============================================================================
# Startup/Shutdown
# =============================================================================

@app.on_event("startup")
async def startup():
    global generator, job_queue
    logger.info("Starting Crispy API...")
    init_db()
    register_beauty_prompts()
    generator = ScriptGeneratorModule()
    job_queue = JobQueue()
    logger.info("Crispy API ready!")


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "crispy"}


@app.post("/upload-url", response_model=UploadUrlResponse)
def create_upload_url(request: UploadUrlRequest):
    """Create a presigned upload URL for MinIO."""
    filename = os.path.basename(request.filename or "")
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")
    prefix = (request.prefix or "inputs").strip("/").replace("\\", "/")
    if ".." in prefix.split("/"):
        raise HTTPException(status_code=400, detail="invalid prefix")
    key = f"{prefix}/{uuid4()}/{filename}"
    expires = int(os.getenv("PRESIGN_EXPIRES_SECONDS", "3600"))
    upload_url = presign_put_url(key, expires, request.content_type)
    return UploadUrlResponse(key=key, upload_url=upload_url, expires_seconds=expires)


@app.get("/options", response_model=OptionsResponse)
async def get_options():
    """Get available generation options"""
    return generator.get_available_options()


@app.post("/jobs", response_model=JobStatusResponse)
def create_job(request: JobCreateRequest):
    """Create a new video processing job."""
    with db_session() as session:
        job = Job(
            status="queued",
            input_data={
                "source_url": request.source_url,
                "input_s3_key": request.input_s3_key,
                "task": request.task,
                "auto_clips": request.auto_clips,
                "transcript_s3_key": request.transcript_s3_key,
                "transcript": request.transcript,
                "segments": request.segments or [],
                "boundary_mode": request.boundary_mode,
                "render_mode": request.render_mode,
                "track_mode": request.track_mode,
                "reels": request.reels,
                "snap_to_silence": request.snap_to_silence,
                "snap_window_sec": request.snap_window_sec,
                "hook_first_cutting": request.hook_first_cutting,
                "hook_window_sec": request.hook_window_sec,
                "hook_min_rms_db": request.hook_min_rms_db,
                "mode": request.mode,
                "metadata": request.metadata,
            },
        )
        session.add(job)
        session.flush()
        job_id = job.id
        created_at = job.created_at
        updated_at = job.updated_at

    if job_queue:
        job_queue.enqueue(job_id)

    return JobStatusResponse(
        id=job_id,
        status="queued",
        links=JobLinks(output=None, clips=[]),
        progress=0.0,
        progress_stage="queued",
        error=None,
        created_at=created_at,
        updated_at=updated_at,
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str):
    """Get job status and output links."""
    with db_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        presign_expires = int(os.getenv("PRESIGN_EXPIRES_SECONDS", "3600"))
        output_link: Optional[str] = None
        if job.output_key:
            output_link = presign_get_url(job.output_key, presign_expires)
        elif job.output_url:
            output_link = job.output_url

        clips_links: list[dict[str, str]] = []
        if job.clips_keys:
            for item in job.clips_keys:
                if isinstance(item, dict) and "key" in item:
                    key = item["key"]
                    clip_id = item.get("id") or key.split("/")[-1]
                    reels_key = item.get("reels_key")
                else:
                    key = item
                    clip_id = str(item).split("/")[-1]
                    reels_key = None
                reels_url: Optional[str] = None
                if reels_key:
                    reels_url = presign_get_url(reels_key, presign_expires)
                clips_links.append(
                    {
                        "id": clip_id,
                        "url": presign_get_url(key, presign_expires),
                        "reels_url": reels_url,
                    }
                )

        return JobStatusResponse(
            id=job.id,
            status=job.status,
            links=JobLinks(output=output_link, clips=clips_links),
            progress=job.progress,
            progress_stage=job.progress_stage,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


@app.post("/generate", response_model=GenerateResponse)
async def generate_scripts(request: GenerateRequest):
    """
    Generate video scripts based on parameters.

    - **niche**: Beauty niche (nails, hair, makeup, general)
    - **status**: User business status (practitioner, academy_owner)
    - **goal**: Content goal (exposure, value, sales)
    - **tone**: Writing tone (professional, casual, energetic, slang)
    - **topic**: Specific topic (optional)
    - **num_scripts**: Number of script variations (1-10)
    - **provider**: AI provider preference (openai, gemini, claude)
    """
    try:
        result = await generator.generate_scripts(
            niche=request.niche,
            status=request.status,
            goal=request.goal,
            tone=request.tone,
            topic=request.topic,
            num_scripts=request.num_scripts,
            provider=request.provider
        )

        return GenerateResponse(
            success=True,
            scripts=[
                ScriptResponse(
                    hook=s.hook,
                    body=s.body,
                    cta=s.cta,
                    hashtags=s.hashtags,
                    music_suggestion=s.music_suggestion,
                    duration_estimate=s.duration_estimate
                )
                for s in result.scripts
            ],
            provider=result.provider_used,
            model=result.model_used,
            tokens_used=result.tokens_used,
            cost_usd=result.cost_usd
        )

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/refine", response_model=ScriptResponse)
async def refine_script(request: RefineRequest):
    """
    Refine an existing script based on user feedback.

    - **script**: The original script to refine
    - **feedback**: User feedback/instructions for refinement
    - **provider**: AI provider preference (optional)
    """
    try:
        original = GeneratedScript(
            hook=request.script.hook,
            body=request.script.body,
            cta=request.script.cta,
            hashtags=request.script.hashtags,
            music_suggestion=request.script.music_suggestion
        )

        refined = await generator.refine_script(
            script=original,
            feedback=request.feedback,
            provider=request.provider
        )

        return ScriptResponse(
            hook=refined.hook,
            body=refined.body,
            cta=refined.cta,
            hashtags=refined.hashtags,
            music_suggestion=refined.music_suggestion,
            duration_estimate=refined.duration_estimate
        )

    except Exception as e:
        logger.error(f"Refinement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Run directly
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

