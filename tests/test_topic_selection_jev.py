from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills" / "newsletter-production" / "scripts" / "topic_selection_jev.py"
)
SPEC = importlib.util.spec_from_file_location("topic_selection_jev", SCRIPT)
assert SPEC and SPEC.loader
jev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jev)

class TopicSelectionJevTests(unittest.TestCase):
    def test_all_decisions_build_official_payload_shape(self):
        state = {"candidate": {"id": "C-001"}, "sources": []}
        for decision in jev.DECISIONS:
            with self.subTest(decision=decision):
                payload = jev.build_payload(decision, state, "jev-latest")
                self.assertEqual(
                    payload["state"], jev.decision_state(decision, state))
                self.assertEqual(payload["model"], "jev-latest")
                self.assertTrue(payload["questions"])

    def test_plan_review_is_a_bounded_jev_gate(self):
        payload = jev.build_payload("plan_review", {
            "period": {"start": "2026-01-01", "end": "2026-01-07"},
            "candidates": [{"id": "TS-1"}],
            "plan": {"weekly": ["TS-1"]},
            "capacity": {"max_outputs": 1},
            "internal_notes": "must not leak",
        }, "jev-latest")
        self.assertEqual(
            payload["questions"]["disposition"]["criteria"]["pass"],
            "配置可交作者或責任編輯做整體決定",
        )
        self.assertNotIn("internal_notes", payload["state"])
        self.assertIn("capacity_feasible", payload["questions"])

    def test_plan_review_accepts_selection_run_shape(self):
        projected = jev.decision_state("plan_review", {
            "run_id": "RUN-1",
            "period": {"start": "2026-01-01", "end": "2026-01-07"},
            "candidate_ids": ["TS-1"],
            "allocation": {"weekly": ["TS-1"]},
            "production_intent": {"weekly": "start"},
            "deferred": [],
            "capacity": {"max_outputs": 1},
            "author_decisions": [],
            "evidence": ["evidence/viability.json"],
            "limitations": [],
            "discovery_coverage": {"complete": True},
            "review": {"status": "passed", "reviewer_role": "fresh"},
        })
        self.assertEqual(projected["candidates"], ["TS-1"])
        self.assertEqual(projected["plan"]["production_intent"], {"weekly": "start"})
        self.assertNotIn("review", projected)

    def test_destination_questions_are_non_exclusive(self):
        questions = jev.build_payload("destinations", {}, "jev-latest")["questions"]
        self.assertEqual(questions["weekly_suitable"]["type"], "noul")
        self.assertEqual(questions["thematic_suitable"]["type"], "noul")
        self.assertEqual(questions["short_suitable"]["type"], "noul")
        self.assertEqual(questions["assessment_status"]["type"], "choice")

    def test_destination_questions_use_upstream_signals_as_evidence_not_a_winner(self):
        questions = jev.build_payload("destinations", {}, "jev-latest")["questions"]
        combined = " ".join(question["instructions"] for question in questions.values())
        self.assertIn("上游分析訊號", combined)
        self.assertIn("格式", combined)
        self.assertIn("不是本輪排程", combined)
        self.assertIn("不得選最高分", combined)
        self.assertIn("不得", questions["assessment_status"]["instructions"])

    def test_contract_versions_mark_upstream_aware_destination_semantics(self):
        self.assertEqual(jev.CONTRACT_VERSION, "newsletter-topic-selection-jev/v5")
        self.assertEqual(
            jev.DECISION_CONTRACT_VERSIONS["destinations"],
            "newsletter-topic-selection-jev/format-readiness/v2",
        )

    def test_decision_projection_uses_signals_without_preanswered_routes(self):
        state = {
            "candidate": {"id": "C-001"},
            "sources": [{"id": "S-1"}],
            "known_gaps": [],
            "related_content": [{"id": "OLD-1"}],
            "upstream_signal_evidence": [{"source_id": "S-1"}],
            "production_context": {
                "weekly": "這段文字會預先暗示週報答案",
            },
            "portfolio_capacity": {"weekly": 1},
        }
        projected = jev.build_payload(
            "destinations", state, "jev-latest")["state"]
        self.assertIn("upstream_signal_evidence", projected)
        self.assertIn("related_content", projected)
        self.assertNotIn("production_context", projected)
        self.assertNotIn("portfolio_capacity", projected)
        relationship = jev.build_payload(
            "relationship", state, "jev-latest")["state"]
        self.assertIn("sources", relationship)
        self.assertNotIn("upstream_signal_evidence", relationship)

    def test_receipt_preserves_exact_projected_state(self):
        state = {
            "candidate": {"id": "C-001"},
            "sources": [],
            "production_context": {"weekly": "hint"},
        }
        payload = jev.build_payload("viability", state, "jev-latest")
        questions = payload["questions"]
        response = {
            "model": "jev-latest",
            "answers": {
                "has_reader_problem": {"type": "noul", "noul": 0.9},
                "has_supported_judgment": {"type": "noul", "noul": 0.8},
                "source_sufficiency": {
                    "type": "score", "score": 2,
                    "probabilities": {"0": 0.0, "1": 0.1, "2": 0.9},
                },
                "disposition": {"type": "choice", "choice": "ready"},
            },
        }
        self.assertEqual(set(response["answers"]), set(questions))
        receipt = jev.build_receipt(
            "viability", state, payload, response)
        self.assertEqual(receipt["state_snapshot"], payload["state"])
        self.assertNotIn("production_context", receipt["state_snapshot"])

    def test_relationship_is_material_handling_not_output_format(self):
        criteria = jev.build_payload(
            "relationship", {}, "jev-latest")["questions"]["disposition"]["criteria"]
        self.assertEqual(
            set(criteria),
            {"distinct", "update", "merge", "link_back", "absorbed", "needs_context"},
        )
        self.assertNotIn("shorten", criteria)

    def test_validate_response_rejects_unknown_choice(self):
        questions = jev.build_payload("viability", {}, "jev-latest")["questions"]
        answers = {
            "has_reader_problem": {"type": "noul", "noul": 0.8},
            "has_supported_judgment": {"type": "noul", "noul": 0.7},
            "source_sufficiency": {
                "type": "score",
                "score": 1.4,
                "probabilities": {"0": 0.1, "1": 0.4, "2": 0.5},
            },
            "disposition": {"type": "choice", "choice": "invented"},
        }
        self.assertEqual(set(answers), set(questions))
        with self.assertRaisesRegex(RuntimeError, "未宣告選項"):
            jev.validate_response("viability", {"answers": answers})

    def test_batch_flag_is_available(self):
        args = jev.parse_args(["viability", "candidates.json", "--batch", "--dry-run"])
        self.assertTrue(args.batch)

    def test_gap_route_uses_explicit_precedence_and_four_routes(self):
        questions = jev.build_payload("gap_route", {}, "jev-latest")["questions"]
        self.assertEqual(
            set(questions["route"]["criteria"]),
            {"retrievable", "safe_fallback", "author_only", "blocking"},
        )
        instructions = questions["route"]["instructions"]
        self.assertLess(instructions.index("查回"), instructions.index("安全縮小"))
        self.assertLess(instructions.index("安全縮小"), instructions.index("問作者"))

    def test_receipt_names_decision_contract_version(self):
        payload = jev.build_payload("gap_route", {}, "jev-latest")
        response = {
            "model": "jev-latest",
            "answers": {
                "is_retrievable": {"type": "noul", "noul": 0.9},
                "safe_fallback_preserves_task": {"type": "noul", "noul": 0.1},
                "requires_author_authority": {"type": "noul", "noul": 0.1},
                "route": {"type": "choice", "choice": "retrievable"},
            },
        }
        receipt = jev.build_receipt("gap_route", {}, payload, response)
        self.assertEqual(
            receipt["decision_contract_version"],
            "newsletter-topic-selection-jev/gap-route/v0",
        )
        self.assertEqual(receipt["outcome"], "retrievable")

    def test_plan_review_rejects_internally_inconsistent_pass(self):
        payload = jev.build_payload("plan_review", {}, "jev-latest")
        response = {
            "model": "jev-latest",
            "answers": {
                "candidate_coverage_sound": {"type": "noul", "noul": 0.8},
                "sources_and_gaps_resolved": {"type": "noul", "noul": 0.45},
                "outputs_independent": {"type": "noul", "noul": 0.8},
                "author_boundaries_respected": {"type": "noul", "noul": 0.9},
                "capacity_feasible": {"type": "noul", "noul": 0.9},
                "disposition": {"type": "choice", "choice": "pass"},
            },
        }
        receipt = jev.build_receipt("plan_review", {}, payload, response)
        self.assertEqual(receipt["jev_outcome"], "pass")
        self.assertEqual(receipt["outcome"], "revise")
        self.assertEqual(receipt["failed_dimensions"], ["sources_and_gaps_resolved"])


if __name__ == "__main__":
    unittest.main()
