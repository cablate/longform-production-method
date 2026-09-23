from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills" / "newsletter-production" / "scripts" / "newsletter_gate_jev.py"
)
SPEC = importlib.util.spec_from_file_location("newsletter_gate_jev", SCRIPT)
assert SPEC and SPEC.loader
jev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jev)


class NewsletterGateJevTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "artifact": {
                "id": "W-TEST", "content_type": "weekly_compilation",
                "content": "主旨：測試\n\n這是一份完整測試稿。",
            },
            "assignment": {"reader_task": "理解測試", "public_boundary": []},
            "sources": [{"locator": "source:test", "content": "測試來源"}],
        }

    def test_all_seven_gates_build_typed_payloads(self):
        self.assertEqual(len(jev.GATES), 7)
        for gate in jev.GATES:
            with self.subTest(gate=gate):
                payload = jev.build_payload(gate, self.state, "jev-latest")
                self.assertEqual(payload["state"], jev.project_state(gate, self.state))
                self.assertIn("disposition", payload["questions"])
                self.assertEqual(payload["questions"]["disposition"]["type"], "choice")

    def test_projection_drops_unrelated_workflow_state(self):
        state = dict(self.state)
        state["internal_retry_notes"] = "不得送給 judge"
        state["delivery_package"] = {"subject": "測試"}
        payload = jev.build_payload("experience", state, "jev-latest")
        self.assertEqual(
            set(payload["state"]), {"artifact", "assignment", "delivery_package"})

    def test_bundle_keeps_gate_decisions_independent(self):
        payload = jev.build_bundle_payload("reader_voice", self.state, "jev-latest")
        self.assertIn("experience__disposition", payload["questions"])
        self.assertIn("sepia__disposition", payload["questions"])
        self.assertNotIn("sources", payload["state"])
        self.assertIn("不得與其他 Gate 平均或互相抵銷",
                      payload["questions"]["sepia__disposition"]["instructions"])

    def test_bundle_response_splits_without_duplicate_usage(self):
        answers = {}
        for gate in jev.GATE_BUNDLES["reader_voice"]:
            for question_id, question in jev.GATES[gate]["questions"].items():
                key = f"{gate}__{question_id}"
                answers[key] = ({"type": "noul", "noul": 0.8}
                                if question["type"] == "noul"
                                else {"type": "choice", "choice": "pass"})
        response = {"model": "jev-test", "usage": {"input_tokens": 10},
                    "answers": answers}
        jev.validate_bundle_response("reader_voice", response)
        split = jev.split_bundle_response("reader_voice", response, "sepia")
        self.assertIsNone(split["usage"])
        self.assertEqual(split["answers"]["disposition"]["choice"], "pass")

    def test_receipt_uses_consistent_disposition_as_formal_outcome(self):
        payload = jev.build_payload("experience", self.state, "jev-latest")
        response = {
            "model": "jev-test",
            "answers": {
                "entry_clear": {"type": "noul", "noul": 0.9},
                "context_sufficient": {"type": "noul", "noul": 0.8},
                "navigation_readable": {"type": "noul", "noul": 0.7},
                "skim_path_clear": {"type": "noul", "noul": 0.8},
                "terminology_load_bounded": {"type": "noul", "noul": 0.9},
                "dependency_light": {"type": "noul", "noul": 0.9},
                "reader_autonomy_preserved": {"type": "noul", "noul": 0.9},
                "disposition": {"type": "choice", "choice": "pass"},
            },
        }
        validated = jev.validate_response("experience", response)
        receipt = jev.build_receipt(
            "experience", self.state, payload, validated, "input.json")
        self.assertEqual(receipt["outcome"], "pass")
        self.assertEqual(receipt["jev_outcome"], "pass")
        self.assertIsNone(receipt["policy_adjustment"])
        self.assertEqual(receipt["authority"], "formal_gate")
        self.assertEqual(receipt["watch_dimensions"], [])
        self.assertNotIn("state_snapshot", receipt)

    def test_pass_with_failed_required_dimension_routes_to_repair(self):
        payload = jev.build_payload("sepia", self.state, "jev-latest")
        response = {
            "model": "jev-test",
            "answers": {
                "structure_natural": {"type": "noul", "noul": 0.8},
                "repetition_controlled": {"type": "noul", "noul": 0.44},
                "rhythm_natural": {"type": "noul", "noul": 0.9},
                "paragraph_rhythm_balanced": {"type": "noul", "noul": 0.8},
                "venue_and_voice_fit": {"type": "noul", "noul": 0.8},
                "disposition": {"type": "choice", "choice": "pass"},
            },
        }
        receipt = jev.build_receipt(
            "sepia", self.state, payload,
            jev.validate_response("sepia", response), "candidate.md")
        self.assertEqual(receipt["jev_outcome"], "pass")
        self.assertEqual(receipt["outcome"], "refactor")
        self.assertEqual(receipt["failed_dimensions"], ["repetition_controlled"])
        self.assertIsNotNone(receipt["policy_adjustment"])

    def test_weak_but_passing_dimension_is_non_blocking_watch(self):
        payload = jev.build_payload("experience", self.state, "jev-latest")
        response = {
            "model": "jev-test",
            "answers": {
                "entry_clear": {"type": "noul", "noul": 0.62},
                "context_sufficient": {"type": "noul", "noul": 0.8},
                "navigation_readable": {"type": "noul", "noul": 0.7},
                "skim_path_clear": {"type": "noul", "noul": 0.8},
                "terminology_load_bounded": {"type": "noul", "noul": 0.9},
                "dependency_light": {"type": "noul", "noul": 0.9},
                "reader_autonomy_preserved": {"type": "noul", "noul": 0.9},
                "disposition": {"type": "choice", "choice": "pass"},
            },
        }
        receipt = jev.build_receipt(
            "experience", self.state, payload,
            jev.validate_response("experience", response), "candidate.md")
        self.assertEqual(receipt["outcome"], "pass")
        self.assertEqual(receipt["watch_dimensions"], ["entry_clear"])

    def test_research_critical_dimensions_cannot_pass_as_watch(self):
        for (gate, target), floor in jev.REQUIRED_FLOORS.items():
            with self.subTest(gate=gate, target=target):
                state = dict(self.state)
                questions = jev.GATES[gate]["questions"]
                answers = {
                    question_id: (
                        {"type": "noul", "noul": 0.64 if question_id == target else 0.9}
                        if question["type"] == "noul"
                        else {"type": "choice", "choice": "pass"}
                    )
                    for question_id, question in questions.items()
                }
                payload = jev.build_payload(gate, state, "jev-latest")
                response = {"model": "jev-test", "answers": answers}
                receipt = jev.build_receipt(
                    gate, state, payload,
                    jev.validate_response(gate, response), f"{gate}.json")
                self.assertEqual(receipt["outcome"], jev.REPAIR_OUTCOME[gate])
                self.assertEqual(receipt["failed_dimensions"], [target])
                self.assertEqual(receipt["required_floors"][target], floor)

    def test_exactly_uncertain_required_dimension_does_not_pass(self):
        payload = jev.build_payload("sepia", self.state, "jev-latest")
        response = {
            "model": "jev-test",
            "answers": {
                "structure_natural": {"type": "noul", "noul": 0.8},
                "repetition_controlled": {"type": "noul", "noul": 0.5},
                "rhythm_natural": {"type": "noul", "noul": 0.9},
                "paragraph_rhythm_balanced": {"type": "noul", "noul": 0.8},
                "venue_and_voice_fit": {"type": "noul", "noul": 0.8},
                "disposition": {"type": "choice", "choice": "pass"},
            },
        }
        receipt = jev.build_receipt(
            "sepia", self.state, payload,
            jev.validate_response("sepia", response), "candidate.md")
        self.assertEqual(receipt["outcome"], "refactor")
        self.assertEqual(receipt["failed_dimensions"], ["repetition_controlled"])

    def test_unknown_choice_is_rejected(self):
        response = {
            "answers": {
                "entry_clear": {"type": "noul", "noul": 0.9},
                "context_sufficient": {"type": "noul", "noul": 0.8},
                "navigation_readable": {"type": "noul", "noul": 0.7},
                "skim_path_clear": {"type": "noul", "noul": 0.8},
                "terminology_load_bounded": {"type": "noul", "noul": 0.9},
                "dependency_light": {"type": "noul", "noul": 0.9},
                "reader_autonomy_preserved": {"type": "noul", "noul": 0.9},
                "disposition": {"type": "choice", "choice": "invented"},
            }
        }
        with self.assertRaisesRegex(RuntimeError, "未宣告選項"):
            jev.validate_response("experience", response)

    def test_dry_run_needs_no_api_key(self):
        args = jev.parse_args(["truth", "input.json", "--dry-run"])
        self.assertTrue(args.dry_run)

    def test_plain_markdown_is_accepted_for_self_contained_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidate.md"
            path.write_text("# 測試稿\n\n完整正文。", encoding="utf-8")
            state = jev.load_state(str(path))
        self.assertEqual(state["artifact"]["id"], "candidate")
        self.assertIn("完整正文", state["artifact"]["content"])

    def test_plain_markdown_is_rejected_for_source_dependent_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidate.md"
            path.write_text("# 測試稿\n\n完整正文。", encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                exit_code = jev.main(["truth", str(path), "--dry-run"])
        self.assertEqual(exit_code, 1)

if __name__ == "__main__":
    unittest.main()
