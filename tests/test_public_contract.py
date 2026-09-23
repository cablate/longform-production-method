from __future__ import annotations

import importlib.util
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
