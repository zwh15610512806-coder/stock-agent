import os
from pathlib import Path


def runtime_cache_path(project_root: Path, filename: str) -> Path:
    if os.environ.get("VERCEL"):
        return Path(os.environ.get("TMPDIR") or "/tmp") / "zhi-tou-terminal" / filename
    return project_root / ".runtime" / filename
