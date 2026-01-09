"""
Crispy API Server - FastAPI web service for script generation
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import asyncio

from modules.script_generator import ScriptGeneratorModule, GeneratedScript
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


# =============================================================================
# Request/Response Models
# =============================================================================

class GenerateRequest(BaseModel):
    """Request for script generation"""
    niche: str = Field(default="general", description="Beauty niche: nails, hair, makeup, general")
    status: str = Field(default="practitioner", description="User status: practitioner, academy_owner")
    goal: str = Field(default="exposure", description="Content goal: exposure, value, sales")
    tone: str = Field(default="casual", description="Tone: professional, casual, energetic, slang")
    topic: Optional[str] = Field(default=None, description="Specific topic (e.g., 'גל ציפורניים')")
    num_scripts: int = Field(default=5, ge=1, le=10, description="Number of scripts (1-10)")
    provider: Optional[str] = Field(default=None, description="AI provider: openai, gemini, claude")

    class Config:
        json_schema_extra = {
            "example": {
                "niche": "nails",
                "status": "practitioner",
                "goal": "exposure",
                "tone": "slang",
                "topic": "גל ציפורניים",
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


# =============================================================================
# Startup/Shutdown
# =============================================================================

@app.on_event("startup")
async def startup():
    global generator
    logger.info("Starting Crispy API...")
    register_beauty_prompts()
    generator = ScriptGeneratorModule()
    logger.info("Crispy API ready!")


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "crispy"}


@app.get("/options", response_model=OptionsResponse)
async def get_options():
    """Get available generation options"""
    return generator.get_available_options()


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
