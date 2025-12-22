import hashlib
import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import Config
from ..core.logging import setup_task_logger

logger = setup_task_logger("OCRImporter")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within_directory(root: Path, target: Path) -> bool:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    return target_resolved == root_resolved or root_resolved in target_resolved.parents


def _safe_extract(zip_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zip_handle:
        for member in zip_handle.infolist():
            member_path = Path(member.filename)
            if member_path.name == "":
                continue
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Unsafe path in zip: {member.filename}")
            target_path = dest_dir / member_path
            if not _is_within_directory(dest_dir, target_path):
                raise ValueError(f"Unsafe extraction path: {member.filename}")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zip_handle.open(member) as source, target_path.open("wb") as target:
                shutil.copyfileobj(source, target)


def _find_manifest_root(extract_root: Path) -> Path:
    manifest_path = extract_root / "manifest.json"
    if manifest_path.exists():
        return extract_root

    for child in extract_root.iterdir():
        if child.is_dir() and (child / "manifest.json").exists():
            return child

    raise FileNotFoundError("manifest.json not found in zip bundle")


def _safe_join(root: Path, rel_path: str) -> Path:
    rel = Path(rel_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Unsafe relative path: {rel_path}")
    abs_path = (root / rel).resolve()
    if not _is_within_directory(root, abs_path):
        raise ValueError(f"Path escapes root: {rel_path}")
    return abs_path


def import_ocr_zip(zip_path: str) -> dict:
    config = Config()
    base_dir = config.temp_dir / "ocr_imports"
    base_dir.mkdir(parents=True, exist_ok=True)

    import_id = f"import_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    import_dir = base_dir / import_id
    bundle_zip = import_dir / "bundle.zip"
    bundle_root = import_dir / "bundle"
    import_dir.mkdir(parents=True, exist_ok=True)
    bundle_root.mkdir(parents=True, exist_ok=True)

    zip_path = Path(zip_path)
    shutil.move(str(zip_path), str(bundle_zip))

    _safe_extract(bundle_zip, bundle_root)
    manifest_root = _find_manifest_root(bundle_root)
    manifest_path = manifest_root / "manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("items", [])

    results: list[dict] = []
    skipped: list[dict] = []

    for item in items:
        item_id = item.get("item_id") or uuid.uuid4().hex
        university_name = (item.get("university_name") or "").strip()
        paths = item.get("paths") or {}
        original_pdf_rel = paths.get("original_pdf")
        original_md_rel = paths.get("original_md")

        if not original_pdf_rel or not original_md_rel:
            skipped.append({"item_id": item_id, "reason": "missing paths.original_pdf or paths.original_md"})
            continue

        try:
            original_pdf_path = _safe_join(manifest_root, original_pdf_rel)
            original_md_path = _safe_join(manifest_root, original_md_rel)
        except ValueError as exc:
            skipped.append({"item_id": item_id, "reason": str(exc)})
            continue

        if not original_pdf_path.exists():
            skipped.append({"item_id": item_id, "reason": "original_pdf not found"})
            continue
        if not original_md_path.exists():
            skipped.append({"item_id": item_id, "reason": "original_md not found"})
            continue

        checksums = item.get("checksums") or {}
        pdf_checksum = checksums.get("original_pdf")
        md_checksum = checksums.get("original_md")
        if pdf_checksum:
            expected = pdf_checksum.replace("sha256:", "")
            actual = _sha256(original_pdf_path)
            if expected and actual != expected:
                skipped.append({"item_id": item_id, "reason": "original_pdf checksum mismatch"})
                continue
        if md_checksum:
            expected = md_checksum.replace("sha256:", "")
            actual = _sha256(original_md_path)
            if expected and actual != expected:
                skipped.append({"item_id": item_id, "reason": "original_md checksum mismatch"})
                continue

        original_filename = item.get("filename") or original_pdf_path.name
        if not university_name:
            university_name = Path(original_filename).stem

        results.append({
            "item_id": item_id,
            "university_name": university_name,
            "original_filename": original_filename,
            "pdf_file_path": str(original_pdf_path),
            "original_md_path": str(original_md_path),
            "page_count": item.get("page_count"),
            "import_id": import_id,
            "import_root": str(manifest_root),
        })

    logger.info(f"OCR import {import_id}: {len(results)} items, {len(skipped)} skipped.")
    return {"import_id": import_id, "items": results, "skipped": skipped}
