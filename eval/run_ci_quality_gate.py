"""与 GitHub Actions 同步的本地离线质量门禁入口。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ("run_agent_platform_eval.py", "Agent production capability suite: Passed 10/10"),
    ("run_resume_evidence_eval.py", "Evidence suites: Passed 7/7"),
)


def main() -> None:
    for script, expected in SCRIPTS:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "eval" / script)],
            cwd=PROJECT_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if result.returncode != 0 or expected not in result.stdout:
            raise RuntimeError(f"{script} failed:\n{result.stdout}\n{result.stderr}")
        print(result.stdout.strip())
    print(f"CI quality gate: Passed {len(SCRIPTS)}/{len(SCRIPTS)}")


if __name__ == "__main__":
    main()
