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
    image_paths: Dict[str, str]
    publication_results: Dict[str, bool]
    publication_errors: Dict[str, List[str]]
