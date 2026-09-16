"""Prompt 作为可发布资产：版本快照、稳定灰度、回滚解析与 Trace 元数据。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
REGISTRY_PATH = PROMPT_DIR / "registry.json"


@dataclass(frozen=True)
class PromptResolution:
    prompt_id: str
    version: str
    content: str
    content_hash: str
    channel: str
    rollout_percent: int
    registry_version: str
    change_summary: str

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "prompt_id": self.prompt_id,
            "version": self.version,
            "content_hash": self.content_hash,
            "channel": self.channel,
            "rollout_percent": self.rollout_percent,
            "registry_version": self.registry_version,
            "change_summary": self.change_summary,
        }


def _load_registry(registry_path: Path | None = None) -> dict:
    target = registry_path or REGISTRY_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def _clamp_rollout(value: str | int | None, default: int) -> int:
    try:
        return max(0, min(100, int(default if value is None else value)))
    except (TypeError, ValueError):
        return default


def _bucket(traffic_key: str) -> int:
    digest = hashlib.sha256(traffic_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def resolve_prompt(
    traffic_key: str | None = None,
    *,
    forced_version: str | None = None,
    registry_path: Path | None = None,
) -> PromptResolution:
    """稳定选择 active/candidate 版本；环境变量可安全冻结或回滚流量。"""
    registry = _load_registry(registry_path)
    versions = registry["versions"]
    requested = forced_version or os.getenv("PROMPT_FORCE_VERSION")
    active = os.getenv("PROMPT_ACTIVE_VERSION") or registry["active_version"]
    candidate = os.getenv("PROMPT_CANDIDATE_VERSION") or registry.get("candidate_version")
    rollout = _clamp_rollout(
        os.getenv("PROMPT_CANDIDATE_ROLLOUT_PERCENT"),
        int(registry.get("candidate_rollout_percent", 0)),
    )

    if requested:
        if requested not in versions:
            raise ValueError(f"unknown_prompt_version:{requested}")
        selected, channel = requested, "forced"
    elif candidate and candidate in versions and rollout and _bucket(traffic_key or "anonymous") < rollout:
        selected, channel = candidate, "candidate"
    else:
        selected, channel = active, "active"

    item = versions.get(selected)
    if not item:
        raise ValueError(f"prompt_not_registered:{selected}")
    content = (PROMPT_DIR / item["file"]).read_text(encoding="utf-8").strip()
    return PromptResolution(
        prompt_id="enterprise-support-agent",
        version=selected,
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        channel=channel,
        rollout_percent=rollout,
        registry_version=registry["registry_version"],
        change_summary=item.get("change_summary", ""),
    )


def get_registry_status(registry_path: Path | None = None) -> dict[str, object]:
    registry = _load_registry(registry_path)
    active = resolve_prompt("status", forced_version=registry["active_version"], registry_path=registry_path)
    candidate_name = registry.get("candidate_version")
    candidate = (
        resolve_prompt("status", forced_version=candidate_name, registry_path=registry_path).to_trace_dict()
        if candidate_name else None
    )
    return {
        "registry_version": registry["registry_version"],
        "active": active.to_trace_dict(),
        "candidate": candidate,
        "candidate_rollout_percent": _clamp_rollout(
            os.getenv("PROMPT_CANDIDATE_ROLLOUT_PERCENT"),
            int(registry.get("candidate_rollout_percent", 0)),
        ),
        "rollback_target": registry.get("rollback_version"),
        "rollback_instruction": "Set PROMPT_FORCE_VERSION to rollback_target, then rerun the regression gate before traffic is reopened.",
    }
