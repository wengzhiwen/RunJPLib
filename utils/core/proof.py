"""
校对证据保存工具
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Optional


def _safe_folder_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "unknown_university"


def save_proof_bundle(university_name: str, markdown_a: str, markdown_b: str, markdown_c: str, base_dir: Optional[Path] = None) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe_name = _safe_folder_name(university_name)

    repo_root = Path(__file__).resolve().parents[2]
    proof_root = base_dir or (repo_root / "proof")
    proof_root.mkdir(parents=True, exist_ok=True)

    folder = proof_root / f"{timestamp}_{safe_name}"
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "A_original.md").write_text(markdown_a, encoding="utf-8")
    (folder / "B_reference.md").write_text(markdown_b, encoding="utf-8")
    (folder / "C_refined.md").write_text(markdown_c, encoding="utf-8")

    return folder
