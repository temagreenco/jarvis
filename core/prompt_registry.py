"""
Prompt Registry - Master Prompts for Crispy Script Generation
Manages prompt templates for different niches, statuses, and content goals.
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from pathlib import Path
import json

from utils.logger import get_logger

logger = get_logger("prompt_registry")


class BeautyNiche(Enum):
    """Beauty industry niches"""
    NAILS = "nails"  # ציפורניים
    HAIR = "hair"  # שיער
    MAKEUP = "makeup"  # איפור
    GENERAL = "general"  # כללי ביוטי


class UserStatus(Enum):
    """User's business status"""
    PRACTITIONER = "practitioner"  # מטפלת / נותנת שירות
    ACADEMY_OWNER = "academy_owner"  # בעלת אקדמיה / מדריכה


class ContentGoal(Enum):
    """Goal of the video content"""
    EXPOSURE = "exposure"  # חשיפה - להגיע לקהל חדש
    VALUE = "value"  # ערך / טיפ - לטפח קהל קיים
    SALES = "sales"  # מכירה - להמיר לפעולה


class ToneStyle(Enum):
    """Tone/style of the script"""
    PROFESSIONAL = "professional"  # מקצועי, רציני
    CASUAL = "casual"  # רגוע, נגיש
    ENERGETIC = "energetic"  # אנרגטי, נלהב
    SLANG = "slang"  # צ'חלה, סלנגי, שפת רחוב


@dataclass
class ScriptOutput:
    """
    Output contract for generated scripts.
    This is the exact structure the AI must return.
    """
    hook: str  # Opening hook (first 3 seconds)
    body: str  # Main content
    cta: str  # Call to action
    hashtags: list[str] = field(default_factory=list)
    music_suggestion: Optional[str] = None
    duration_estimate: str = "15-30 seconds"


@dataclass
class GenerationRequest:
    """Request for script generation"""
    niche: BeautyNiche
    status: UserStatus
    goal: ContentGoal
    tone: ToneStyle = ToneStyle.CASUAL
    specific_topic: Optional[str] = None  # e.g., "גל ציפורניים", "בלונד קר"
    num_variations: int = 5
    language: str = "hebrew"


@dataclass
class MasterPrompt:
    """A master prompt template"""
    id: str
    status: UserStatus
    goal: ContentGoal
    niche: BeautyNiche
    system_prompt: str
    user_prompt_template: str
    output_schema: dict
    version: str = "1.0"
    metadata: dict = field(default_factory=dict)


# Output JSON Schema for script generation
SCRIPT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "scripts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hook": {"type": "string", "description": "Opening hook - first 3 seconds"},
                    "body": {"type": "string", "description": "Main content of the script"},
                    "cta": {"type": "string", "description": "Call to action"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "music_suggestion": {"type": "string"},
                    "duration_estimate": {"type": "string"}
                },
                "required": ["hook", "body", "cta"]
            }
        }
    },
    "required": ["scripts"]
}


class PromptRegistry:
    """
    Registry for all Master Prompts.
    Prompts are indexed by (status, goal, niche) tuple.
    """

    def __init__(self):
        self.prompts: dict[tuple, MasterPrompt] = {}
        self.language_layers: dict[BeautyNiche, dict] = {}
        self._load_default_prompts()

    def _get_key(self, status: UserStatus, goal: ContentGoal, niche: BeautyNiche) -> tuple:
        return (status.value, goal.value, niche.value)

    def register(self, prompt: MasterPrompt) -> None:
        """Register a master prompt"""
        key = self._get_key(prompt.status, prompt.goal, prompt.niche)
        self.prompts[key] = prompt
        logger.info(f"Registered prompt: {prompt.id}")

    def get(
        self,
        status: UserStatus,
        goal: ContentGoal,
        niche: BeautyNiche = BeautyNiche.GENERAL
    ) -> Optional[MasterPrompt]:
        """Get a prompt by criteria, with fallback to general niche"""
        key = self._get_key(status, goal, niche)
        prompt = self.prompts.get(key)

        # Fallback to general niche if specific not found
        if not prompt and niche != BeautyNiche.GENERAL:
            general_key = self._get_key(status, goal, BeautyNiche.GENERAL)
            prompt = self.prompts.get(general_key)

        return prompt

    def set_language_layer(self, niche: BeautyNiche, layer: dict) -> None:
        """Set language/slang layer for a niche"""
        self.language_layers[niche] = layer

    def get_language_layer(self, niche: BeautyNiche) -> dict:
        """Get language layer for niche"""
        return self.language_layers.get(niche, {})

    def build_prompt(self, request: GenerationRequest) -> tuple[str, str]:
        """
        Build final system and user prompts from a generation request.
        Returns (system_prompt, user_prompt)
        """
        master = self.get(request.status, request.goal, request.niche)

        if not master:
            raise ValueError(
                f"No prompt found for: status={request.status.value}, "
                f"goal={request.goal.value}, niche={request.niche.value}"
            )

        # Get language layer
        lang_layer = self.get_language_layer(request.niche)

        # Build system prompt with language layer
        system = master.system_prompt

        if lang_layer:
            vocab_section = self._format_language_layer(lang_layer)
            system = f"{system}\n\n{vocab_section}"

        # Add tone instructions
        system += f"\n\n## טון הכתיבה\n{self._get_tone_instructions(request.tone)}"

        # Build user prompt
        user = master.user_prompt_template.format(
            niche=self._translate_niche(request.niche),
            status=self._translate_status(request.status),
            goal=self._translate_goal(request.goal),
            topic=request.specific_topic or "כללי",
            num_variations=request.num_variations
        )

        return system, user

    def _format_language_layer(self, layer: dict) -> str:
        """Format language layer into prompt section"""
        sections = ["## שפה וסגנון"]

        if "allowed_words" in layer:
            sections.append(f"מילים מומלצות: {', '.join(layer['allowed_words'])}")

        if "forbidden_words" in layer:
            sections.append(f"מילים להימנע מהן: {', '.join(layer['forbidden_words'])}")

        if "slang" in layer:
            sections.append(f"סלנג מקובל: {', '.join(layer['slang'])}")

        if "examples" in layer:
            sections.append("\nדוגמאות לשפה טבעית:")
            for ex in layer["examples"]:
                sections.append(f"- {ex}")

        return "\n".join(sections)

    def _get_tone_instructions(self, tone: ToneStyle) -> str:
        """Get tone-specific instructions"""
        tones = {
            ToneStyle.PROFESSIONAL: """
כתוב בטון מקצועי ורציני. השתמש במונחים מקצועיים אבל הסבר אותם.
השפה צריכה להיות ברורה, מדויקת, ומשדרת מומחיות.""",

            ToneStyle.CASUAL: """
כתוב בטון רגוע ונגיש, כמו שיחה בין חברות.
תהיה חמה ואותנטית, בלי להיות רשמית מדי.""",

            ToneStyle.ENERGETIC: """
כתוב בטון אנרגטי ונלהב! תשתמש בקריאות קצרות.
תעביר התלהבות ואנרגיה חיובית. משפטים קצרים ודינמיים.""",

            ToneStyle.SLANG: """
כתוב בסלנג יומיומי, כמו שבחורה צעירה מדברת עם החברות שלה.
תשתמש בביטויים כמו: "וואלה", "יאללה", "חיים שלי", "מהממת", "נשבע לך".
הימנע ממילים גבוהות או רשמיות."""
        }
        return tones.get(tone, tones[ToneStyle.CASUAL])

    def _translate_niche(self, niche: BeautyNiche) -> str:
        translations = {
            BeautyNiche.NAILS: "ציפורניים",
            BeautyNiche.HAIR: "שיער",
            BeautyNiche.MAKEUP: "איפור",
            BeautyNiche.GENERAL: "ביוטי"
        }
        return translations.get(niche, "ביוטי")

    def _translate_status(self, status: UserStatus) -> str:
        translations = {
            UserStatus.PRACTITIONER: "מטפלת / נותנת שירות",
            UserStatus.ACADEMY_OWNER: "בעלת אקדמיה / מדריכה"
        }
        return translations.get(status, "מקצוענית")

    def _translate_goal(self, goal: ContentGoal) -> str:
        translations = {
            ContentGoal.EXPOSURE: "חשיפה וגידול קהל",
            ContentGoal.VALUE: "ערך וטיפים לקהל קיים",
            ContentGoal.SALES: "מכירה והנעה לפעולה"
        }
        return translations.get(goal, "תוכן")

    def _load_default_prompts(self) -> None:
        """Load default master prompts"""
        # Will be populated by the prompts module
        pass

    def export_prompts(self, path: Path) -> None:
        """Export all prompts to JSON file"""
        data = {
            "prompts": [
                {
                    "id": p.id,
                    "status": p.status.value,
                    "goal": p.goal.value,
                    "niche": p.niche.value,
                    "system_prompt": p.system_prompt,
                    "user_prompt_template": p.user_prompt_template,
                    "version": p.version
                }
                for p in self.prompts.values()
            ],
            "language_layers": {
                k.value: v for k, v in self.language_layers.items()
            }
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info(f"Exported {len(self.prompts)} prompts to {path}")

    def import_prompts(self, path: Path) -> None:
        """Import prompts from JSON file"""
        data = json.loads(path.read_text())

        for p in data.get("prompts", []):
            prompt = MasterPrompt(
                id=p["id"],
                status=UserStatus(p["status"]),
                goal=ContentGoal(p["goal"]),
                niche=BeautyNiche(p["niche"]),
                system_prompt=p["system_prompt"],
                user_prompt_template=p["user_prompt_template"],
                output_schema=SCRIPT_OUTPUT_SCHEMA,
                version=p.get("version", "1.0")
            )
            self.register(prompt)

        for niche, layer in data.get("language_layers", {}).items():
            self.set_language_layer(BeautyNiche(niche), layer)

        logger.info(f"Imported {len(data.get('prompts', []))} prompts from {path}")


# Global registry instance
_registry: Optional[PromptRegistry] = None


def get_registry() -> PromptRegistry:
    """Get global prompt registry instance"""
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry
