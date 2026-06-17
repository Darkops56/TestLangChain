from typing import TypedDict, List, Dict

class PlatformContent(TypedDict):
    text: str
    image_prompt: str
    is_valid: bool
    errors: List[str]

class MultiPlatformState(TypedDict):
    user_prompt: str
    platforms: List[str]
    outputs: Dict[str, PlatformContent]
    retry_count: int
    platform_feedback: Dict[str, str]
    is_approved: bool
