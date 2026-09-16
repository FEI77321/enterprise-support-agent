"""只读 Prompt Registry 状态接口，便于演示当前 active/candidate/rollback 边界。"""

from fastapi import APIRouter

from app.prompt_registry import get_registry_status


router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("/status")
def prompt_status() -> dict[str, object]:
    return get_registry_status()
