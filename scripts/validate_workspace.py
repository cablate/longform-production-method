#!/usr/bin/env python3
"""Validate the public workspace boundary without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


REQUIRED_PACKET_FIELDS = {"schema_version", "id", "kind", "content", "provenance", "public_boundary"}
SECRET_PATTERNS = (
    re.compile(r"(?:api[_-]?key|token|secret)\s*[:=]\s*[\"']?[A-Za-z0-9_-]{16,}", re.I),
    re.compile(r"gh[opusr]_[A-Za-z0-9]{20,}"),
)


def validate(root: Path, allow_placeholders: bool = False) -> list[str]:
    errors: list[str] = []
    project = root / "PROJECT.md"
    if not project.is_file():
        errors.append("missing PROJECT.md")
    else:
        text = project.read_text(encoding="utf-8")
        for heading in ("## 1. 素材來源", "## 2. 取得方式", "## 3. 作者與讀者"):
            if heading not in text:
                errors.append(f"PROJECT.md missing section: {heading}")
        if not allow_placeholders and "<" in text and ">" in text:
            errors.append("PROJECT.md still contains fill-in placeholders")

    source_dir = root / "sources"
    packets = sorted(source_dir.glob("*.json")) if source_dir.is_dir() else []
    if not packets:
        errors.append("sources/ contains no JSON source packets")
    seen: set[str] = set()
    for path in packets:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.name}: packet must be an object")
            continue
        missing = REQUIRED_PACKET_FIELDS - set(value)
        if missing:
            errors.append(f"{path.name}: missing fields: {', '.join(sorted(missing))}")
        if value.get("schema_version") != "source-packet/v1":
            errors.append(f"{path.name}: unsupported schema_version")
        packet_id = value.get("id")
        if not isinstance(packet_id, str) or not packet_id.strip():
            errors.append(f"{path.name}: id must be a non-empty string")
        elif packet_id in seen:
            errors.append(f"{path.name}: duplicate id: {packet_id}")
        else:
            seen.add(packet_id)
        if not isinstance(value.get("content"), str) or not value.get("content", "").strip():
            errors.append(f"{path.name}: content must be non-empty")

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".txt", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            errors.append(f"possible secret in {path.relative_to(root)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--allow-placeholders", action="store_true")
    args = parser.parse_args()
    errors = validate(args.workspace.resolve(), args.allow_placeholders)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("workspace valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

