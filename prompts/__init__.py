"""
Prompts package - Master prompts for content generation
"""
from prompts.beauty_prompts import register_beauty_prompts

# Auto-register prompts on import
register_beauty_prompts()
