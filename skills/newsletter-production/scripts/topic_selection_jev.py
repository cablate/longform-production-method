#!/usr/bin/env python3
"""Call TypeSafe JEV for the bounded judgments in topic selection.

This is intentionally a small prompt-first pilot boundary. It does not own the
topic-selection workflow, inventory, routing, or author decisions. Input and
output are JSON so an AI orchestrator can prepare state and preserve receipts.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
CONTRACT_VERSION = "newsletter-topic-selection-jev/v5"
OUTCOME_POLICY_VERSION = "newsletter-topic-selection-jev/outcome-policy/v1"
DECISION_CONTRACT_VERSIONS = {
    "viability": "newsletter-topic-selection-jev/viability/v1",
    "relationship": "newsletter-topic-selection-jev/relationship/v1",
    "destinations": "newsletter-topic-selection-jev/format-readiness/v2",
    "gap_route": "newsletter-topic-selection-jev/gap-route/v0",
    "plan_review": "newsletter-topic-selection-jev/plan-review/v2",
}
DECISIONS = tuple(DECISION_CONTRACT_VERSIONS)


def _viability_questions() -> dict[str, Any]:
    return {
        "has_reader_problem": {
            "type": "noul",
            "instructions": "候選是否提出一個清楚、可辨識的讀者問題？",
            "criteria": {
                "true": "讀者情境與要解決的問題都可辨識",
                "false": "只有話題、情緒、例子或模糊標籤",
            },
        },
        "has_supported_judgment": {
            "type": "noul",
            "instructions": "來源是否支持一個可交付給讀者的核心判斷？",
            "criteria": {
                "true": "來源直接支持候選的核心判斷",
                "false": "判斷主要依賴未提供的推論或作者意圖",
            },
        },
        "source_sufficiency": {
            "type": "score",
            "instructions": "目前來源足以讓候選進入庫存比較的程度",
            "criteria": [
                "不足：只是片段，缺少不可替代的上下文",
                "部分：題目可辨識，但仍缺特定來源或作者決定",
                "足夠：讀者問題與核心判斷都有可追溯支持",
            ],
        },
        "disposition": {
            "type": "choice",
            "instructions": "候選目前最適合進入哪個狀態？",
            "criteria": {
                "ready": "來源足以進入庫存與舊內容比較",
                "needs_context": "缺少可以查回的父文、來源或上下文",
                "needs_author": "只缺作者立場、本人經驗或公開邊界",
                "hold": "目前尚不能形成可工作的題目，保留潛力與重啟條件",
            },
        },
    }


def _relationship_questions() -> dict[str, Any]:
    return {
        "same_reader_problem": {
            "type": "noul",
            "instructions": "候選與相關既有內容是否處理同一個讀者問題？",
            "criteria": {
                "true": "讀者情境與需要完成的判斷實質相同",
                "false": "讀者問題或使用情境有實質差異",
            },
        },
        "same_core_answer": {
            "type": "noul",
            "instructions": "候選與相關既有內容是否給出實質相同的核心答案？",
            "criteria": {
                "true": "主要結論、做法與限制沒有實質新增",
                "false": "核心答案、證據、反例或用途有實質不同",
            },
        },
        "added_value": {
            "type": "score",
            "instructions": "相較提供的相關內容，候選帶來多少新增讀者價值？",
            "criteria": [
                "沒有：只有換句話說或重複材料",
                "有限：補充情境、例子或小幅更新",
                "實質：新增問題、答案、證據、反例、用途或重要更新",
            ],
        },
        "disposition": {
            "type": "choice",
            "instructions": "候選和提供的相關內容之間，最適合採取哪種處理？",
            "criteria": {
                "distinct": "保留為獨立候選",
                "update": "主要價值是更新既有內容",
                "merge": "併入既有候選，避免另起重複題目",
                "link_back": "新候選可成立，但使用時應連回既有內容",
                "absorbed": "已被既有內容完整吸收，關閉獨立候選身分",
                "needs_context": "目前提供的短名單或來源不足以可靠比較",
            },
        },
    }


def _destination_questions() -> dict[str, Any]:
    return {
        "weekly_suitable": {
            "type": "noul",
            "instructions": (
                "根據候選的全部來源、可用的上游分析訊號、庫存關係與缺口，"
                "候選目前是否具備成為可獨立理解週報單元的內容條件？"
                "這不是本輪排程或優先級判斷。"),
            "criteria": {
                "true": "有限篇幅內補足背景後，讀者可得到一項完整進展",
                "false": "放入週報會過度壓縮、重複或無法獨立成立",
            },
        },
        "thematic_suitable": {
            "type": "noul",
            "instructions": (
                "根據候選的全部來源、可用的上游分析訊號、庫存關係與缺口，"
                "候選目前是否具備展開成主題式電子報的內容條件？"
                "這不是本輪排程或優先級判斷。"),
            "criteria": {
                "true": "材料足以形成完整判斷弧線、證據與適用邊界",
                "false": "目前只能加長素材，還不足以形成完整文章",
            },
        },
        "short_suitable": {
            "type": "noul",
            "instructions": (
                "根據候選的全部來源、可用的上游分析訊號、庫存關係與缺口，"
                "候選目前是否具備成為短札記或社群短文的內容條件？"
                "這不是本輪排程或優先級判斷。"),
            "criteria": {
                "true": "有一個無須大量前情也能成立的核心觀察",
                "false": "脫離完整上下文會失真、空泛或無法理解",
            },
        },
        "assessment_status": {
            "type": "choice",
            "instructions": (
                "目前資料是否足以判斷候選對三種格式的內容準備度？"
                "這不是判斷內容是否已經可直接生產或應在本輪啟動；因缺證據而得出"
                "某格式尚未準備好，仍可是完整判斷。來源包提供的用途潛力"
                "只是上游證據，不是本題的答案；不得選最高分或覆寫上游 receipt。"),
            "criteria": {
                "complete": "資料足以判斷格式準備度，即使結果是尚未準備好",
                "needs_context": "缺少的資料會讓格式準備度本身無法下結論",
            },
        },
    }


def _gap_route_questions() -> dict[str, Any]:
    return {
        "is_retrievable": {
            "type": "noul",
            "instructions": "缺口是否能用已提供的定位、來源或可用工具直接查回？",
            "criteria": {
                "true": "已有具體定位、來源或查詢路徑，AI 可採取明確查回動作",
                "false": "沒有可執行的查回路徑，或缺的其實是作者決定而非資料",
            },
        },
        "safe_fallback_preserves_task": {
            "type": "noul",
            "instructions": "若略過、匿名化或縮小主張，是否仍能保留這個候選的核心讀者任務？",
            "criteria": {
                "true": "採安全 fallback 後仍回答同一個核心讀者問題，只降低範圍或細節",
                "false": "fallback 會改變核心問題、主要立場或使候選不再成立",
            },
        },
        "requires_author_authority": {
            "type": "noul",
            "instructions": "剩餘缺口是否必須由作者本人決定，且會實質改變候選內容？",
            "criteria": {
                "true": "涉及作者立場、本人經驗、承諾或公開邊界，AI 與外部來源不能代答",
                "false": "屬可查資料、一般編輯取捨，或已有安全 fallback",
            },
        },
        "route": {
            "type": "choice",
            "instructions": (
                "依固定優先序選擇缺口的下一步：先判斷能否查回；不能查回時，"
                "再判斷能否在保留核心讀者任務下安全縮小；兩者皆否，才判斷是否"
                "必須問作者；若目前沒有任何可行解法則暫停。只選一項。"
            ),
            "criteria": {
                "retrievable": "已有具體查回路徑；AI 應先取得資料，不問作者",
                "safe_fallback": "無法查回，但可略過、匿名化或縮小主張而保留核心讀者任務",
                "author_only": "無法查回、沒有安全 fallback，且只有作者能決定立場、本人經驗、承諾或公開邊界",
                "blocking": "無法查回、沒有安全 fallback，且作者決定也不能在目前條件下解決；等待外部來源或狀態改變",
            },
        },
    }


def _plan_review_questions() -> dict[str, Any]:
    return {
        "candidate_coverage_sound": {
            "type": "noul",
            "instructions": "本輪可用候選是否都被配置、明確暫緩或保留，沒有遺漏與重複 owner？",
            "criteria": {"true": "每個候選去向唯一且可追溯", "false": "有遺漏、重複配置或去向互相衝突"},
        },
        "sources_and_gaps_resolved": {
            "type": "noul",
            "instructions": "每個啟動項目的直接來源、已知缺口與 fallback 是否足以進入 brief？",
            "criteria": {"true": "來源與缺口路由明確", "false": "核心來源缺失或把未知當成已成立"},
        },
        "outputs_independent": {
            "type": "noul",
            "instructions": "週報、主題式電子報與短札記之間是否各有獨立讀者任務與新增價值，不是同一內容重複包裝？",
            "criteria": {"true": "各輸出去向的任務與價值可區分", "false": "跨用途重複、互相欠答案或共享同一承重內容"},
        },
        "author_boundaries_respected": {
            "type": "noul",
            "instructions": "配置是否保留作者決定、公開邊界與未授權內容，沒有由 AI 代為承諾？",
            "criteria": {"true": "作者權限與公開邊界均被保留", "false": "配置越過作者決定或公開範圍"},
        },
        "capacity_feasible": {
            "type": "noul",
            "instructions": "本輪啟動數量與先後是否符合提供的產能限制，未把內容適合誤當成全部同時生產？",
            "criteria": {"true": "啟動量、優先序與暫緩項目符合限制", "false": "過載、互斥或沒有實際停點"},
        },
        "disposition": {
            "type": "choice",
            "instructions": "決定整體配置是否可交作者或責任編輯；只有五項必要條件都成立才 pass。",
            "criteria": {
                "pass": "配置可交作者或責任編輯做整體決定",
                "revise": "現有證據足夠，但配置、去向或邊界需要修正",
                "needs_context": "必須補候選、來源、庫存比較或產能資料才能判斷",
                "author_only": "只剩作者或責任編輯才能決定的優先序、公開範圍或取捨",
            },
        },
    }


QUESTION_BUILDERS = {
    "viability": _viability_questions,
    "relationship": _relationship_questions,
    "destinations": _destination_questions,
    "gap_route": _gap_route_questions,
    "plan_review": _plan_review_questions,
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decision_state(decision: str, state: Any) -> Any:
    """Return the minimum evidence projection for one bounded decision.

    Candidate discovery may contain editorial hints such as
    ``production_context``.  Those hints must not pre-answer JEV's format
    readiness questions.  Source-provided signals are included as evidence snapshots,
    while scheduling and portfolio capacity remain outside JEV.
    """
    if not isinstance(state, Mapping) or decision == "gap_route":
        return state
    if decision == "plan_review" and "run_id" in state:
        return {
            "period": state.get("period"),
            "candidates": state.get("_plan_review_candidates", state.get("candidate_ids")),
            "plan": {
                "allocation": state.get("allocation"),
                "production_intent": state.get("production_intent"),
                "deferred": state.get("deferred"),
            },
            "capacity": state.get("capacity"),
            "author_decisions": state.get("author_decisions"),
            "source_receipts": state.get("evidence"),
            "known_gaps": state.get("limitations"),
            "discovery_coverage": state.get("discovery_coverage"),
            "source_summary": state.get("source_summary"),
        }
    shared = (
        "candidate", "sources", "known_gaps", "upstream_signal_evidence",
    )
    by_decision = {
        "viability": shared,
        "relationship": ("candidate", "sources", "related_content", "known_gaps"),
        "destinations": (*shared, "related_content"),
        "plan_review": (
            "period", "candidates", "plan", "capacity", "author_decisions",
            "source_receipts", "known_gaps", "discovery_coverage",
            "source_summary",
        ),
    }
    return {
        key: state[key]
        for key in by_decision[decision]
        if key in state
    }


def state_identity(state: Any) -> str:
    digest = hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def load_state(path: str) -> Any:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"輸入不是合法 JSON：{exc.msg}") from exc
    if not isinstance(value, (str, list, dict)):
        raise ValueError("state 必須是 JSON string、object 或 array")
    return value


def hydrate_plan_review_state(state: Any, input_path: str) -> Any:
    """Attach compact topic-owner evidence when a selection run is the input."""
    if (not isinstance(state, dict) or "run_id" not in state
            or not isinstance(state.get("candidate_ids"), list)
            or input_path == "-"):
        return state
    run_path = Path(input_path).resolve()
    if len(run_path.parents) < 3:
        return state
    items_root = run_path.parents[2] / "topic-items"
    candidates = []
    for candidate_id in state["candidate_ids"]:
        item_path = items_root / f"{candidate_id}.json"
        if not item_path.is_file():
            candidates.append({"id": candidate_id, "missing_owner": True})
            continue
        item = json.loads(item_path.read_text(encoding="utf-8"))
        candidates.append({
            key: item.get(key)
            for key in (
                "id", "title", "reader_problem", "core_judgment",
                "availability", "sources", "known_gaps", "relationship",
                "destination_assessment", "author_decisions",
            )
        })
    enriched = dict(state)
    enriched["_plan_review_candidates"] = candidates
    return enriched


def build_payload(decision: str, state: Any, model: str) -> dict[str, Any]:
    if decision not in QUESTION_BUILDERS:
        raise ValueError(f"未知判斷類型：{decision}")
    return {
        "state": decision_state(decision, state),
        "model": model,
        "questions": QUESTION_BUILDERS[decision](),
    }


def load_api_key() -> str:
    value = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not value and os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value = str(winreg.QueryValueEx(key, "TYPESAFE_API_KEY")[0]).strip()
        except (FileNotFoundError, OSError):
            value = ""
    if not value:
        raise RuntimeError("尚未設定 TYPESAFE_API_KEY")
    return value


def call_jev(payload: Mapping[str, Any], *, timeout: float = 30.0,
             attempts: int = 3) -> dict[str, Any]:
    key = load_api_key()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict):
                raise RuntimeError("JEV 回應不是 JSON object")
            return value
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 529} or attempt == attempts - 1:
                detail = exc.read().decode("utf-8", errors="replace")[:2000]
                raise RuntimeError(
                    f"JEV 請求失敗（HTTP {exc.code}）：{detail}") from exc
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise RuntimeError("JEV 連線失敗") from exc
        time.sleep(0.25 * (2 ** attempt))
    raise RuntimeError("JEV 請求失敗") from last_error


def validate_response(decision: str, response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError("JEV 回應不是 JSON object")
    answers = response.get("answers")
    expected = QUESTION_BUILDERS[decision]()
    if not isinstance(answers, dict) or set(answers) != set(expected):
        raise RuntimeError("JEV answers 與宣告的問題不一致")
    for question_id, question in expected.items():
        answer = answers.get(question_id)
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise RuntimeError(f"JEV answer {question_id} 類型不一致")
        if question["type"] == "choice":
            choice = answer.get("choice")
            if choice not in question["criteria"]:
                raise RuntimeError(f"JEV answer {question_id} 回傳未宣告選項")
        elif question["type"] == "noul":
            value = answer.get("noul")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise RuntimeError(f"JEV answer {question_id} noul 超出 0–1")
        else:
            probabilities = answer.get("probabilities")
            if not isinstance(probabilities, dict):
                raise RuntimeError(f"JEV answer {question_id} 缺少 probabilities")
    return response


def build_receipt(decision: str, state: Any, payload: Mapping[str, Any],
                  response: Mapping[str, Any]) -> dict[str, Any]:
    usage = response.get("usage")
    projected_state = payload["state"]
    outcome_question = {
        "viability": "disposition",
        "relationship": "disposition",
        "destinations": "assessment_status",
        "gap_route": "route",
        "plan_review": "disposition",
    }[decision]
    jev_outcome = response["answers"][outcome_question]["choice"]
    failed_dimensions = []
    outcome = jev_outcome
    policy_adjustment = None
    if decision == "plan_review":
        failed_dimensions = [
            question_id
            for question_id, question in QUESTION_BUILDERS[decision]().items()
            if question["type"] == "noul"
            and response["answers"][question_id]["noul"] < 0.5
        ]
        if jev_outcome == "pass" and failed_dimensions:
            outcome = "revise"
            policy_adjustment = "pass_rejected_due_to_failed_required_dimension"
    return {
        "contract_version": CONTRACT_VERSION,
        "outcome_policy_version": OUTCOME_POLICY_VERSION,
        "decision_contract_version": DECISION_CONTRACT_VERSIONS[decision],
        "decision": decision,
        "outcome": outcome,
        "jev_outcome": jev_outcome,
        "policy_adjustment": policy_adjustment,
        "failed_dimensions": failed_dimensions,
        "state_identity": state_identity(projected_state),
        "state_snapshot": projected_state,
        "model_requested": payload["model"],
        "model_returned": response.get("model"),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "answers": response["answers"],
        "usage": usage if isinstance(usage, dict) else None,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用 TypeSafe JEV 執行選題流程中的有限判斷")
    parser.add_argument("decision", choices=DECISIONS)
    parser.add_argument("input", help="state JSON 檔案；使用 - 從 stdin 讀取")
    parser.add_argument("--output", help="寫入結果 JSON；省略時輸出至 stdout")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--batch", action="store_true",
        help="將輸入的 JSON array 視為多個獨立 state 依序判斷")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只輸出將送出的 payload，不讀 API key、不呼叫 API")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        state = load_state(args.input)
        if args.decision == "plan_review":
            state = hydrate_plan_review_state(state, args.input)
        if args.batch:
            if not isinstance(state, list):
                raise ValueError("--batch 需要輸入 JSON array")
            batch_results = []
            for index, item in enumerate(state):
                payload = build_payload(args.decision, item, args.model)
                candidate = item.get("candidate") if isinstance(item, dict) else None
                item_id = candidate.get("id") if isinstance(candidate, dict) else None
                if args.dry_run:
                    item_result: Mapping[str, Any] = payload
                else:
                    response = validate_response(
                        args.decision, call_jev(payload, timeout=args.timeout))
                    item_result = build_receipt(
                        args.decision, item, payload, response)
                batch_results.append({
                    "index": index,
                    "candidate_id": item_id,
                    "result": item_result,
                })
            result: Mapping[str, Any] = {
                "contract_version": CONTRACT_VERSION,
                "decision_contract_version": DECISION_CONTRACT_VERSIONS[args.decision],
                "decision": args.decision,
                "batch_count": len(batch_results),
                "results": batch_results,
            }
        else:
            payload = build_payload(args.decision, state, args.model)
            if args.dry_run:
                result = payload
            else:
                response = validate_response(
                    args.decision, call_jev(payload, timeout=args.timeout))
                result = build_receipt(args.decision, state, payload, response)
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
