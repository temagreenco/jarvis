"""
Crispy Script Generator Module
Generates viral video scripts for beauty professionals.
"""
import json
import asyncio
from typing import Optional
from dataclasses import dataclass, field

from modules.base_module import BaseModule, TaskResult
from core.ai_providers import (
    AIProviderManager, AIMessage, AIResponse, ProviderType,
    create_ai_manager_from_settings
)
from core.prompt_registry import (
    PromptRegistry, GenerationRequest, ScriptOutput,
    BeautyNiche, UserStatus, ContentGoal, ToneStyle,
    SCRIPT_OUTPUT_SCHEMA, get_registry
)
from config.settings import get_settings
from utils.logger import get_logger


@dataclass
class GeneratedScript:
    """A single generated script"""
    hook: str
    body: str
    cta: str
    hashtags: list[str] = field(default_factory=list)
    music_suggestion: str = ""
    duration_estimate: str = "15-30 seconds"
    tone: str = ""

    def to_dict(self) -> dict:
        return {
            "hook": self.hook,
            "body": self.body,
            "cta": self.cta,
            "hashtags": self.hashtags,
            "music_suggestion": self.music_suggestion,
            "duration_estimate": self.duration_estimate,
            "tone": self.tone
        }

    def to_full_script(self) -> str:
        """Convert to full readable script"""
        parts = [
            f"🎬 HOOK:\n{self.hook}",
            f"\n📝 BODY:\n{self.body}",
            f"\n📢 CTA:\n{self.cta}"
        ]
        if self.hashtags:
            parts.append(f"\n#️⃣ HASHTAGS:\n{' '.join(self.hashtags)}")
        if self.music_suggestion:
            parts.append(f"\n🎵 MUSIC: {self.music_suggestion}")
        return "\n".join(parts)


@dataclass
class GenerationResult:
    """Result of script generation"""
    scripts: list[GeneratedScript]
    provider_used: str
    model_used: str
    tokens_used: int
    cost_usd: float
    metadata: dict = field(default_factory=dict)


class ScriptGeneratorModule(BaseModule):
    """
    Crispy - AI Script Generator for Beauty Professionals

    Generates viral video scripts (Reels/TikTok) tailored for:
    - Nail technicians
    - Hair stylists
    - Makeup artists
    - Academy owners

    Features:
    - Multi-provider AI (OpenAI, Gemini, Claude)
    - Hebrew language optimized
    - Slang and natural speech
    - Multiple tone styles
    - Structured output (hook/body/CTA)
    """

    name = "script_generator"
    description = "Crispy - Generate viral video scripts for beauty professionals"
    version = "1.0.0"

    # Keywords for task routing
    keywords = [
        "script", "תסריט", "crispy", "reel", "ריל", "tiktok", "טיקטוק",
        "video content", "תוכן וידאו", "beauty", "ביוטי", "nails", "ציפורניים",
        "hair", "שיער", "makeup", "איפור"
    ]

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.registry = get_registry()
        self.ai_manager: Optional[AIProviderManager] = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy initialization of AI manager"""
        if not self._initialized:
            self.ai_manager = create_ai_manager_from_settings(self.settings)
            self._initialized = True
            self.logger.info("Script generator initialized with AI providers")

    def can_handle(self, task: str) -> bool:
        """Check if this module can handle the task"""
        task_lower = task.lower()
        return any(kw in task_lower for kw in self.keywords)

    def execute(self, task: str, **kwargs) -> TaskResult:
        """Execute script generation synchronously"""
        # Run async generation in sync context
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(self.generate_scripts(**kwargs))
            return TaskResult(
                success=True,
                data=result,
                metadata={
                    "provider": result.provider_used,
                    "model": result.model_used,
                    "scripts_count": len(result.scripts),
                    "cost_usd": result.cost_usd
                }
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            loop.close()

    async def generate_scripts(
        self,
        niche: str = "general",
        status: str = "practitioner",
        goal: str = "exposure",
        tone: str = "casual",
        topic: Optional[str] = None,
        num_scripts: int = 5,
        provider: Optional[str] = None,
        **kwargs
    ) -> GenerationResult:
        """
        Generate video scripts based on parameters.

        Args:
            niche: Beauty niche (nails, hair, makeup, general)
            status: User status (practitioner, academy_owner)
            goal: Content goal (exposure, value, sales)
            tone: Writing tone (professional, casual, energetic, slang)
            topic: Specific topic (optional)
            num_scripts: Number of script variations
            provider: Preferred AI provider (openai, gemini, claude)

        Returns:
            GenerationResult with list of scripts
        """
        self._ensure_initialized()

        # Parse enums
        try:
            niche_enum = BeautyNiche(niche.lower())
        except ValueError:
            niche_enum = BeautyNiche.GENERAL

        try:
            status_enum = UserStatus(status.lower())
        except ValueError:
            status_enum = UserStatus.PRACTITIONER

        try:
            goal_enum = ContentGoal(goal.lower())
        except ValueError:
            goal_enum = ContentGoal.EXPOSURE

        try:
            tone_enum = ToneStyle(tone.lower())
        except ValueError:
            tone_enum = ToneStyle.CASUAL

        # Build request
        request = GenerationRequest(
            niche=niche_enum,
            status=status_enum,
            goal=goal_enum,
            tone=tone_enum,
            specific_topic=topic,
            num_variations=num_scripts
        )

        # Build prompts
        system_prompt, user_prompt = self.registry.build_prompt(request)

        # Prepare messages
        messages = [
            AIMessage(role="system", content=system_prompt),
            AIMessage(role="user", content=user_prompt)
        ]

        # Select provider
        preferred = None
        if provider:
            provider_map = {
                "openai": ProviderType.OPENAI,
                "gpt": ProviderType.OPENAI,
                "gemini": ProviderType.GEMINI,
                "google": ProviderType.GEMINI,
                "claude": ProviderType.CLAUDE,
                "anthropic": ProviderType.CLAUDE
            }
            preferred = provider_map.get(provider.lower())

        # Generate
        self.logger.info(f"Generating {num_scripts} scripts for {niche}/{status}/{goal}...")

        response = await self.ai_manager.generate(
            messages=messages,
            preferred_provider=preferred,
            temperature=0.8,  # Higher for creativity
            max_tokens=3000,
            json_mode=True
        )

        # Parse response
        scripts = self._parse_scripts(response.content, tone_enum)

        return GenerationResult(
            scripts=scripts,
            provider_used=response.provider.value,
            model_used=response.model,
            tokens_used=response.tokens_used,
            cost_usd=response.cost_usd,
            metadata=response.metadata
        )

    def _parse_scripts(self, content: str, tone: ToneStyle) -> list[GeneratedScript]:
        """Parse AI response into structured scripts"""
        try:
            data = json.loads(content)
            scripts_data = data.get("scripts", [])
        except json.JSONDecodeError:
            # Try to extract JSON from response
            self.logger.warning("Failed to parse JSON, attempting extraction...")
            import re
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                data = json.loads(match.group())
                scripts_data = data.get("scripts", [])
            else:
                raise ValueError("Could not parse AI response as JSON")

        scripts = []
        for s in scripts_data:
            script = GeneratedScript(
                hook=s.get("hook", ""),
                body=s.get("body", ""),
                cta=s.get("cta", ""),
                hashtags=s.get("hashtags", []),
                music_suggestion=s.get("music_suggestion", ""),
                duration_estimate=s.get("duration_estimate", "15-30 seconds"),
                tone=tone.value
            )
            scripts.append(script)

        return scripts

    async def refine_script(
        self,
        script: GeneratedScript,
        feedback: str,
        provider: Optional[str] = None
    ) -> GeneratedScript:
        """
        Refine a script based on user feedback.

        Args:
            script: The script to refine
            feedback: User feedback/instructions
            provider: Preferred AI provider
        """
        self._ensure_initialized()

        system_prompt = """אתה עוזר לדייק תסריטים לסרטוני וידאו.
המשתמשת נתנה משוב על תסריט קיים. עליך לשפר אותו לפי הבקשה שלה.
שמור על המבנה: hook, body, cta.
החזר JSON בפורמט: {"hook": "...", "body": "...", "cta": "...", "hashtags": [...]}"""

        user_prompt = f"""התסריט המקורי:

HOOK: {script.hook}

BODY: {script.body}

CTA: {script.cta}

---
משוב המשתמשת: {feedback}

אנא דייק את התסריט לפי המשוב."""

        messages = [
            AIMessage(role="system", content=system_prompt),
            AIMessage(role="user", content=user_prompt)
        ]

        preferred = None
        if provider:
            provider_map = {
                "openai": ProviderType.OPENAI,
                "gemini": ProviderType.GEMINI,
                "claude": ProviderType.CLAUDE
            }
            preferred = provider_map.get(provider.lower())

        response = await self.ai_manager.generate(
            messages=messages,
            preferred_provider=preferred,
            temperature=0.5,
            max_tokens=1500,
            json_mode=True
        )

        data = json.loads(response.content)

        return GeneratedScript(
            hook=data.get("hook", script.hook),
            body=data.get("body", script.body),
            cta=data.get("cta", script.cta),
            hashtags=data.get("hashtags", script.hashtags),
            music_suggestion=script.music_suggestion,
            tone=script.tone
        )

    def get_available_options(self) -> dict:
        """Get all available generation options"""
        return {
            "niches": [n.value for n in BeautyNiche],
            "statuses": [s.value for s in UserStatus],
            "goals": [g.value for g in ContentGoal],
            "tones": [t.value for t in ToneStyle],
            "providers": ["openai", "gemini", "claude"]
        }


# Factory function
def get_script_generator() -> ScriptGeneratorModule:
    """Get script generator module instance"""
    return ScriptGeneratorModule()
