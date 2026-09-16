"""验证长期记忆只写明确偏好、可覆盖冲突、隔离 owner 且遵守 TTL。"""

from __future__ import annotations

from datetime import datetime, timezone
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.database import get_connection
from app.memory_service import expire_memories, get_active_memories, write_explicit_memory


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "memory.db"
        first = write_explicit_memory("memory-owner-a", "请记住我喜欢中文、简洁的回答", database)
        updated = write_explicit_memory("memory-owner-a", "请记住我偏好带技术细节的中文回答", database)
        sensitive = write_explicit_memory("memory-owner-a", "请记住我的密码是 123456", database)
        implicit = write_explicit_memory("memory-owner-a", "我今天在家办公", database)
        owner_items = get_active_memories("memory-owner-a", database_path=database)
        other_items = get_active_memories("memory-owner-b", database_path=database)
        connection = get_connection(database)
        try:
            with connection:
                connection.execute("UPDATE agent_memories SET expires_at = ?", ("2000-01-01T00:00:00+00:00",))
        finally:
            connection.close()
        expired_count = expire_memories(database)
        checks = [
            first.action == "written", updated.action == "updated",
            sensitive.action == "reject", implicit.action == "skip",
            len(owner_items) == 1 and "技术细节" in owner_items[0]["memory_value"],
            other_items == [], expired_count == 1 and get_active_memories("memory-owner-a", database_path=database) == [],
        ]
    assert all(checks), checks
    print(f"Long-term memory contract: Passed {len(checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
