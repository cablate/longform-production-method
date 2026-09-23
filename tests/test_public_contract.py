from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_workspace", ROOT / "scripts" / "validate_workspace.py"
)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class PublicContractTests(unittest.TestCase):
    def test_starter_is_valid_when_placeholders_are_explicitly_allowed(self):
        errors = validator.validate(ROOT / "examples" / "starter", allow_placeholders=True)
        self.assertEqual(errors, [])

    def test_missing_project_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            errors = validator.validate(Path(directory), allow_placeholders=True)
        self.assertIn("missing PROJECT.md", errors)

    def test_markdown_relative_links_resolve(self):
        link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
        missing: list[str] = []
        for path in ROOT.rglob("*.md"):
            for target in link_pattern.findall(path.read_text(encoding="utf-8")):
                clean = target.split("#", 1)[0]
                if not clean or "://" in clean or clean.startswith("mailto:"):
                    continue
                if not (path.parent / clean).resolve().exists():
                    missing.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [])

    def test_public_repository_has_no_private_adapter_residue(self):
        forbidden = ("threads" + "2", "threads_" + "post:",
                     "production" + ".node", "production" + ".gate_reviews",
                     "se" + "pia")
        hits: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.suffix == ".pyc":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
