"""Prompt Registry 契约与版本回归：快照、哈希、稳定灰度、强制回滚和 Trace 关联。"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from eval_path import setup_backend_path

setup_backend_path()

from app.agent import handle_message
from app.prompt_registry import get_registry_status, resolve_prompt
from app.trace_store import get_trace


def main() -> None:
    checks: list[tuple[str, bool]] = []
    status = get_registry_status()
    active = resolve_prompt("stable-session")
    forced = resolve_prompt("stable-session", forced_version="support-agent-v2.1")
    checks.extend([
        ("registry_has_active_and_candidate", status["active"]["version"] == "support-agent-v2.0" and status["candidate"]["version"] == "support-agent-v2.1"),
        ("prompt_snapshot_has_content_hash", len(active.content_hash) == 64 and active.content),
        ("forced_candidate_resolution", forced.version == "support-agent-v2.1" and forced.channel == "forced"),
        ("stable_active_resolution", resolve_prompt("stable-session").version == active.version),
        ("rollback_target_is_declared", status["rollback_target"] == "support-agent-v2.0"),
    ])
    with TemporaryDirectory() as directory:
        previous_trace_db = os.environ.get("TRACE_DATABASE_PATH")
        previous_force = os.environ.get("PROMPT_FORCE_VERSION")
        os.environ["TRACE_DATABASE_PATH"] = str(Path(directory) / "trace.db")
        os.environ["PROMPT_FORCE_VERSION"] = "support-agent-v2.1"
        try:
            response = handle_message("VPN 720 错误怎么办", request_id="prompt-registry-001")
            trace = get_trace("prompt-registry-001", Path(directory) / "trace.db")
            checks.extend([
                ("response_records_forced_version", response.prompt.get("version") == "support-agent-v2.1"),
                (
                    "trace_has_prompt_resolution_span",
                    trace is not None and any(
                        span["span_type"] == "prompt" and span["payload"].get("content_hash")
                        for span in trace["spans"]
                    ),
                ),
            ])
        finally:
            if previous_trace_db is None:
                os.environ.pop("TRACE_DATABASE_PATH", None)
            else:
                os.environ["TRACE_DATABASE_PATH"] = previous_trace_db
            if previous_force is None:
                os.environ.pop("PROMPT_FORCE_VERSION", None)
            else:
                os.environ["PROMPT_FORCE_VERSION"] = previous_force
    failed = [name for name, passed in checks if not passed]
    if failed:
        raise SystemExit("Prompt registry contract failed: " + ", ".join(failed))
    print(f"Prompt Registry contract: Passed {len(checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
