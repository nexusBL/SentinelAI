from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_step(name: str, command: list[str], cwd: Path) -> None:
    print(f"[dev-check] {name}: {' '.join(command)}")
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    python_executable = sys.executable

    run_step(
        "compileall",
        [
            python_executable,
            "-m",
            "compileall",
            ".",
        ],
        repo_root,
    )
    run_step("pytest", [python_executable, "-m", "pytest"], repo_root)
    run_step("smoke_test", [python_executable, str(repo_root / "scripts" / "smoke_test.py")], repo_root)
    print("[dev-check] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
