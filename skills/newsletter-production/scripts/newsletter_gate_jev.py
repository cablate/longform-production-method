"""Run one lightweight TypeSafe JEV quality gate for a newsletter artifact."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
CONTRACT_VERSION = "newsletter-jev-gates/v17"
OUTCOME_POLICY_VERSION = "newsletter-jev-gate-outcome-policy/v5"
STATE_PROJECTION_VERSION = "newsletter-jev-state-projection/v1"
PASS_FLOOR = 0.5
WATCH_FLOOR = 0.65

# Research-derived load-bearing dimensions may not pass as a weak watch.  The
# general 0.5 floor still applies elsewhere; these four need stronger evidence
# because they decide whether the artifact is the right kind of newsletter and
# whether a reader can actually use it without coercion.
REQUIRED_FLOORS: dict[tuple[str, str], float] = {
    ("brief", "content_route_fit"): WATCH_FLOOR,
    ("depth", "route_specific_value_delivered"): WATCH_FLOOR,
    ("experience", "skim_path_clear"): WATCH_FLOOR,
    ("experience", "reader_autonomy_preserved"): WATCH_FLOOR,
}

# JEV judges semantics; this deterministic guard only prevents an internally
# inconsistent receipt from saying pass while a required condition misses its
# declared floor, or from blocking when no required condition failed.
REPAIR_OUTCOME = {
    "brief": "revise",
    "truth": "revise",
    "depth": "revise",
    "experience": "revise",
    "fidelity": "revise",
    "sepia": "refactor",
    "final": "revise",
}

STANDARD_GATES = ("brief", "truth", "depth", "experience", "fidelity", "sepia")

# A Gate sees only the evidence needed for its own decision.  This prevents a
# generic state object from silently increasing cost or influencing a judge
# with unrelated workflow metadata.
GATE_STATE_KEYS: dict[str, tuple[str, ...]] = {
    "brief": ("artifact", "assignment", "sources", "claim_source_map",
              "related_content"),
    "truth": ("artifact", "assignment", "sources", "claim_source_map"),
    "depth": ("artifact", "assignment", "sources", "claim_source_map"),
    "experience": ("artifact", "assignment", "delivery_package"),
    "fidelity": ("artifact", "assignment", "sources", "claim_source_map"),
    "sepia": ("artifact", "assignment", "voice_reference", "sepia_process"),
    "final": ("artifact", "assignment", "current_artifact_identity",
              "delivery_package", "brief_receipt", "prior_gate_receipts",
              "version_binding"),
}

# These bundles share one request body while preserving separate question IDs,
# dispositions, policy checks, and child receipts.  They are review batching,
# not a merged score.
GATE_BUNDLES: dict[str, tuple[str, ...]] = {
    "evidence": ("truth", "depth", "fidelity"),
    "reader_voice": ("experience", "sepia"),
}


def _noul(instructions: str) -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": instructions,
        "criteria": {"true": "成立", "false": "不成立"},
    }


def _choice(instructions: str, criteria: Mapping[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions,
            "criteria": dict(criteria)}


GATES: dict[str, dict[str, Any]] = {
    "brief": {
        "version": "newsletter-jev-gate/brief/v5",
        "questions": {
            "reader_task_clear": _noul("brief 是否指明可辨認的目標讀者，以及讀完後要形成的理解、判斷或行動？『人人看得懂』『高品質』『有深度』等成品形容不算讀者任務。"),
            "content_route_fit": _noul("先核對 assignment.target_content_type 與 brief 宣告的類型／做法是否一致；若兩者直接衝突，且 assignment 沒有允許改線，此項不成立。再判斷該路線是否適合本期任務，而不是套模型熟悉的文章骨架：判斷／案例型深文應交代有依據的起點理解、更準確的問題、會改變判斷的證據及可遷移邊界；週報編選應交代期間、入選單元與編選價值，不必假裝只有一個 thesis；短札記、通知、策展或社群內容依自身任務成立。若類型或完成條件無法辨認，此項也不成立。"),
            "claims_supported": _noul("依 sources 與 claim_source_map 檢查：brief 的每個承重主張是否可追溯到直接來源，或清楚標成由哪些來源推導的分析？不要求來源逐字說出合理推論，但不得把缺乏來源的外部事實、成效或普遍因果當既定前提。"),
            "scope_bounded": _noul("適用條件、非目標與不可外推範圍是否足以控制文章？"),
            "distinct_value": _noul("brief 是否明寫相對既有內容的新問題、新組合、新推理或新用途？若沒有比較基準或只宣稱『更完整／更深入』，此條不成立。"),
            "disposition": _choice("決定 brief 下一步；只有 reader_task_clear、content_route_fit、claims_supported、scope_bounded、distinct_value 均成立且沒有關鍵缺口才 pass。", {
                "pass": "可以投入完整寫作",
                "revise": "現有資料足夠，但 brief 的任務、範圍或表述需修正",
                "recover_sources": "核心主張或比較缺少可查回的直接來源",
                "author_only": "只缺作者本人才能決定的立場、經驗或公開邊界",
            }),
        },
    },
    "truth": {
        "version": "newsletter-jev-gate/truth/v4",
        "questions": {
            "facts_and_quotes_supported": _noul("先按 claim_source_map 對應正文主張與指定來源，再把提供的 sources 視為唯一外部證據：正文中可外部核對的事實、數字、引句、事件與時間敘述是否均獲直接支持？透明標示為作者分析、條件推演、可能性或假設的內容不要求來源逐字出現，也不要因為來源沒有逐字寫出合理分析就判為不成立；但若分析冒充外部事實，仍不成立。"),
            "causality_restrained": _noul("正文是否避免把相關、觀察或單一案例擴寫成未證實因果或通則？"),
            "first_person_supported": _noul("所有第一人稱經驗、立場與感受是否來自作者實際表達？"),
            "public_scope_safe": _noul("正文是否遵守可公開範圍，沒有洩露未授權識別、內容或承諾？"),
            "disposition": _choice("只依本 Gate 的 facts_and_quotes_supported、causality_restrained、first_person_supported、public_scope_safe 四項決定下一步，不可用其他面向的優點抵銷來源問題，也不另加未列出的標準。四項都較可能成立時選 pass。只有正文必要的可核對事實或引句缺乏直接來源、且不能安全刪除或降格時才選 recover_sources；透明的作者分析不得因此被當成來源缺口。", {
                "pass": "所有真實性與公開範圍條件成立",
                "revise": "可用刪除、降格、縮小或局部改寫安全修正",
                "recover_sources": "核心內容必須補直接來源才能成立",
                "author_only": "只有作者本人能確認經驗、立場或公開許可",
            }),
        },
    },
    "depth": {
        "version": "newsletter-jev-gate/depth/v4",
        "questions": {
            "promise_completed": _noul("正文是否真正完成主旨與本期讀者任務，而非只提到結論？"),
            "source_capacity_used": _noul("先依 assignment 的 content_promise 與 claim_source_map 界定本篇真正相關的來源容量：其中承重的場景、推理、取捨或反例是否獲得足夠展開？來源包可能包含供查核但不屬於本篇承諾的其他細節，不要求為了用完材料而寫入正文。"),
            "reasoning_complete": _noul("讀者是否能沿證據理解判斷如何形成，沒有關鍵推理跳躍？"),
            "route_specific_value_delivered": _noul("正文是否完成該內容路線特有的價值？判斷／案例型深文要讓讀者看得出原理解為何不夠、更準確的問題、哪些證據改變判斷，以及能如何轉用；週報編選要讓各單元可獨立理解並保留情境、作者判斷或張力，不得因沒有單一論點而判失敗；短札記、通知、策展與社群內容依 assignment 的承諾判斷，不強迫補成深文。"),
            "transfer_bounded": _noul("可轉用條件、不適用情境與限制是否保留？"),
            "disposition": _choice("只依本 Gate 的 promise_completed、source_capacity_used、reasoning_complete、route_specific_value_delivered、transfer_bounded 五項決定下一步，不以字數或段落數代替完成度，也不另加未列出的標準。五項都較可能成立時選 pass；至少一項較可能不成立時才選 revise 或 recover_sources。", {
                "pass": "文章已完成承諾且保留必要深度",
                "revise": "現有來源足以補回或重組缺少的理解",
                "recover_sources": "核心理解缺少不可替代的來源",
            }),
        },
    },
    "experience": {
        "version": "newsletter-jev-gate/experience/v3",
        "questions": {
            "entry_clear": _noul("目標讀者是否能從開頭自然進入這篇處理的問題及為何值得繼續？若開頭先向讀者辯解題目很散、不是要硬湊、本文將如何編排，或評論自己的寫作策略，而不是直接進入可辨認的現場或問題，此項不成立；多話題週報不必假裝只有一個論點。"),
            "context_sufficient": _noul("沒看過前文的讀者是否仍有足夠背景與術語說明？"),
            "navigation_readable": _noul("段落順序、資訊密度與轉折是否讓讀者能中斷後接回？"),
            "skim_path_clear": _noul("以略讀者角度只看已提供的主旨／預覽、開頭、資訊性小標或段落入口、重要轉折與結尾，是否仍能辨認本篇問題、主要推進與收穫？沒有小標的短文不因此失敗；長文若必須逐字讀完才知道各段在做什麼，此項不成立。"),
            "terminology_load_bounded": _noul("專有名詞與英文是否只在理解主題確有需要時保留，並在第一次出現時有足夠情境讓目標讀者跟上？不要因為是英文就判失敗；要攔的是不必要的縮寫、內部製作標籤，以及需要讀者先解碼流程黑話才能理解正文的寫法。"),
            "dependency_light": _noul("正文是否不必依賴外部連結、前一期或未說明行動才能成立？"),
            "reader_autonomy_preserved": _noul("正文與下一步是否保留讀者選擇，不以恐懼、羞恥、身份威脅、虛假急迫或假親密逼迫接受主張或行動？強而有根據的立場不算操控；若有 CTA，應與本期內容自然相關且不把回覆、轉寄、填表、購買等多個動作同時變成必要任務。"),
            "disposition": _choice("只依本 Gate 的 entry_clear、context_sufficient、navigation_readable、skim_path_clear、terminology_load_bounded、dependency_light、reader_autonomy_preserved 決定閱讀體驗下一步；七項都較可能成立時選 pass。", {
                "pass": "閱讀入口、背景、導航與依賴都成立",
                "revise": "需要局部重排、補背景或降低閱讀負擔",
            }),
        },
    },
    "fidelity": {
        "version": "newsletter-jev-gate/fidelity/v5",
        "questions": {
            "author_subject_present": _noul("優先以 evidence_roles 含 author_voice 的來源判斷（未標記時再依內容辨認）：來源原本可辨認的作者主體、判斷與張力是否仍存在？process_record 可支持流程事實，但不能單獨代替作者聲音。"),
            "stance_preserved": _noul("正文是否保留作者的立場、確定程度與情緒方向？"),
            "first_person_retained": _noul("優先以 evidence_roles 含 author_voice 的來源判斷（未標記時再依內容辨認）：其中原本已有且對本篇承諾承重的第一人稱、場景與具體細節，是否仍以可辨認形式存在，而沒有被摘要成無人稱報告。process_record 不算作者聲音；不要因正文另有透明標示的作者分析或推論就判此項不成立，第一人稱是否獲來源支持已由 truth Gate 負責。"),
            "sensitive_exposure_safe": _noul("正文是否沒有加入來源與公開邊界以外、非論述必要的個資、客戶／學員識別、內部內容或敏感細節？"),
            "not_merely_paraphrased": _noul("正文是否在保留作者原意下，加入可指認的組合、推理、取捨、適用邊界或用途，而不是只把舊內容換字拉長？"),
            "disposition": _choice("只依本 Gate 的 author_subject_present、stance_preserved、first_person_retained、sensitive_exposure_safe、not_merely_paraphrased 五項決定下一步，不另加未列出的標準。五項都較可能成立時選 pass；只有無法從現有來源判斷承重作者內容時才選 recover_sources，現有來源足以局部恢復時選 revise。", {
                "pass": "作者主體、立場、第一人稱與內容邊界均保留",
                "revise": "現有來源足以恢復作者內容或移除失真",
                "recover_sources": "必須回查完整原文或作者回覆鏈",
                "author_only": "只有作者本人能決定立場、敏感範圍或是否公開",
            }),
        },
    },
    "sepia": {
        "version": "newsletter-jev-gate/sepia/v3",
        "questions": {
            "structure_natural": _noul("文章是否避免可預測、過度工整或同模板換題目的結構？"),
            "repetition_controlled": _noul("是否避免在沒有新增證據或推理時反覆總結、連續使用『不是 A 而是 B／不只是 A 更是 B』、或在段尾替讀者重複下結論？有明確修辭功能且只出現一次的回環不算缺陷。"),
            "rhythm_natural": _noul("句群、段落、轉折與語氣是否有符合內容的自然變化，而不是連續用短句與句號製造刻意節拍，也不是把每句獨立成段或把所有句子拉成同樣長？"),
            "paragraph_rhythm_balanced": _noul("同一個意思裡的原因、轉折、補充與例子，是否能在適當處連成可呼吸的段落；需要停頓時才斷句或分段？本項不要求長句，也不要求一段一句，而是判斷長短句與段落邊界是否服務理解。"),
            "venue_and_voice_fit": _noul("文字是否符合 assignment 指定的發表場域，以及 voice_reference 提供的作者聲音依據，而非中性報告腔或模型自行想像的語氣？"),
            "disposition": _choice("決定 Sepia 後製下一步；不得以刪短必要內容換取自然感。", {
                "pass": "沒有需要處理的實質 AI 味或場域失真",
                "refactor": "主線成立，只需局部後製並保存原意",
                "recreate_candidate": "作者主體、內容容量或全文節奏已結構性失真，另建候選而不覆蓋原稿",
            }),
        },
    },
    "final": {
        "version": "newsletter-jev-gate/final/v6",
        "questions": {
            "exact_version_ready": _noul("依 version_binding 檢查：待交付內容是否是目前確切版本，且 truth、depth、experience、fidelity、sepia receipts 都綁定此版本？brief receipt 本來綁定 production brief，不應因其 artifact identity 與正文不同而判失敗。"),
            "internal_boundary_clean": _noul("只檢查 artifact.content，不把 Gate input 中本來就存在的 receipts、assignment、version_binding 或其他審查資料算成正文外漏。正文是否沒有提示詞、blocker、receipt、審查狀態、待辦、敏感欄位，或『本篇如何經過 Fidelity／Depth／Sepia』等自身幕後製作紀錄？若文章主題本來就在談 JEV、Gate、Skill、workflow 或內容流程，為了說明普遍方法而出現這些詞並不算外漏；要攔的是把這一篇的實際內部產製與審查狀態直接寫給讀者。"),
            "package_consistent": _noul("主旨、預覽、正文與交付說明是否一致且沒有過度承諾？"),
            "assets_ready": _noul("assignment／delivery package 宣告為必要的連結、圖片、格式與正文邊界是否存在且可用？明確宣告不需要的資產，其缺席視為 ready；未說明是否必要則不能直接推定 ready。"),
            "disposition": _choice("決定是否可把確切版本交作者審閱；pass 不等於作者核准或寄送。", {
                "pass": "可以交作者審閱這個確切版本",
                "revise": "交付包或正文仍有可由 AI 修正的問題",
                "author_only": "只剩作者對確切版本的接受或公開決定",
            }),
        },
    },
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def identity(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        canonical_json(value).encode("utf-8")).hexdigest()


def load_state(path: str) -> dict[str, Any]:
    source_path = None if path == "-" else Path(path)
    raw = sys.stdin.read() if source_path is None else source_path.read_text(encoding="utf-8")
    if source_path is not None and source_path.suffix.lower() not in {".json", ".jsonl"}:
        if not raw.strip():
            raise ValueError("Gate artifact 不可為空")
        return {
            "artifact": {
                "id": source_path.stem,
                "content_type": "unspecified",
                "content": raw,
            },
            "assignment": {},
            "sources": [],
            "input_note": "直接稿件模式只適合不需外部來源的 Gate；truth、depth、fidelity 應使用完整 JSON input。",
        }
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Gate input 必須是 JSON object")
    artifact = value.get("artifact")
    if (not isinstance(artifact, dict)
            or not isinstance(artifact.get("content"), str)
            or not artifact["content"].strip()):
        raise ValueError("Gate input 缺少 artifact.content")
    return value


def project_state(gate: str, state: Mapping[str, Any]) -> dict[str, Any]:
    if gate not in GATES:
        raise ValueError(f"未知 Gate：{gate}")
    return {key: state[key] for key in GATE_STATE_KEYS[gate] if key in state}


def build_payload(gate: str, state: Mapping[str, Any], model: str) -> dict[str, Any]:
    if gate not in GATES:
        raise ValueError(f"未知 Gate：{gate}")
    return {"state": project_state(gate, state), "model": model,
            "questions": GATES[gate]["questions"]}


def build_bundle_payload(bundle: str, state: Mapping[str, Any],
                         model: str) -> dict[str, Any]:
    if bundle not in GATE_BUNDLES:
        raise ValueError(f"未知 Gate bundle：{bundle}")
    gates = GATE_BUNDLES[bundle]
    keys = {key for gate in gates for key in GATE_STATE_KEYS[gate]}
    projected = {key: state[key] for key in state if key in keys}
    questions: dict[str, Any] = {}
    for gate in gates:
        for question_id, question in GATES[gate]["questions"].items():
            bundled = dict(question)
            bundled["instructions"] = (
                f"[{gate} Gate；只依本 Gate 的問題獨立判斷，不得與其他 Gate "
                f"平均或互相抵銷。] {question['instructions']}"
            )
            questions[f"{gate}__{question_id}"] = bundled
    return {"state": projected, "model": model, "questions": questions}


def validate_bundle_response(bundle: str, response: Any) -> dict[str, Any]:
    if bundle not in GATE_BUNDLES:
        raise ValueError(f"未知 Gate bundle：{bundle}")
    if not isinstance(response, dict):
        raise RuntimeError("JEV bundle 回應不是 JSON object")
    expected = {
        f"{gate}__{question_id}"
        for gate in GATE_BUNDLES[bundle]
        for question_id in GATES[gate]["questions"]
    }
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != expected:
        raise RuntimeError("JEV bundle answers 與 Gate 問題不一致")
    for gate in GATE_BUNDLES[bundle]:
        split_bundle_response(bundle, response, gate)
    return response


def split_bundle_response(bundle: str, response: Mapping[str, Any],
                          gate: str) -> dict[str, Any]:
    if bundle not in GATE_BUNDLES or gate not in GATE_BUNDLES[bundle]:
        raise ValueError(f"{gate} 不屬於 Gate bundle：{bundle}")
    answers = response.get("answers")
    if not isinstance(answers, Mapping):
        raise RuntimeError("JEV bundle 回應缺少 answers")
    split = {
        question_id: answers[f"{gate}__{question_id}"]
        for question_id in GATES[gate]["questions"]
    }
    return validate_response(gate, {
        "model": response.get("model"),
        "answers": split,
        # Usage belongs to the bundle request and must not be counted once per
        # child Gate.  The bundle receipt is the accounting authority.
        "usage": None,
    })


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


def call_jev(payload: Mapping[str, Any], *, timeout: float = 60.0,
             attempts: int = 3) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(ENDPOINT, data=body, headers={
        "Authorization": f"Bearer {load_api_key()}",
        "Content-Type": "application/json",
    }, method="POST")
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
            if exc.code not in {429, 502, 503, 504, 529} or attempt == attempts - 1:
                detail = exc.read().decode("utf-8", errors="replace")[:2000]
                raise RuntimeError(f"JEV 請求失敗（HTTP {exc.code}）：{detail}") from exc
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise RuntimeError("JEV 連線失敗") from exc
        time.sleep(0.25 * (2 ** attempt))
    raise RuntimeError("JEV 請求失敗") from last_error


def validate_response(gate: str, response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError("JEV 回應不是 JSON object")
    questions = GATES[gate]["questions"]
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise RuntimeError("JEV answers 與 Gate 問題不一致")
    for question_id, question in questions.items():
        answer = answers.get(question_id)
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise RuntimeError(f"JEV answer {question_id} 類型不一致")
        if question["type"] == "noul":
            value = answer.get("noul")
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not 0 <= value <= 1):
                raise RuntimeError(f"JEV answer {question_id} noul 超出 0–1")
        else:
            if answer.get("choice") not in question["criteria"]:
                raise RuntimeError(f"JEV answer {question_id} 回傳未宣告選項")
    return response


def build_receipt(gate: str, state: Mapping[str, Any], payload: Mapping[str, Any],
                  response: Mapping[str, Any], input_ref: str) -> dict[str, Any]:
    artifact = state["artifact"]
    jev_outcome = response["answers"]["disposition"]["choice"]
    dimension_floors = {
        question_id: REQUIRED_FLOORS.get((gate, question_id), PASS_FLOOR)
        for question_id, question in GATES[gate]["questions"].items()
        if question["type"] == "noul"
    }
    failed_dimensions = [
        question_id
        for question_id, question in GATES[gate]["questions"].items()
        if question["type"] == "noul"
        and response["answers"][question_id]["noul"] <= dimension_floors[question_id]
    ]
    watch_dimensions = [
        question_id
        for question_id, question in GATES[gate]["questions"].items()
        if question["type"] == "noul"
        and dimension_floors[question_id] < response["answers"][question_id]["noul"] < WATCH_FLOOR
    ]
    outcome = jev_outcome
    policy_adjustment = None
    if outcome == "pass" and failed_dimensions:
        outcome = REPAIR_OUTCOME[gate]
        policy_adjustment = "pass_rejected_due_to_failed_required_dimension"
    elif outcome != "pass" and not failed_dimensions:
        outcome = "pass"
        policy_adjustment = "non_pass_rejected_due_to_no_failed_required_dimension"
    return {
        "schema_version": "newsletter-jev-gate-receipt/v1",
        "contract_version": CONTRACT_VERSION,
        "outcome_policy_version": OUTCOME_POLICY_VERSION,
        "gate_contract_version": GATES[gate]["version"],
        "gate": gate,
        "outcome": outcome,
        "jev_outcome": jev_outcome,
        "policy_adjustment": policy_adjustment,
        "failed_dimensions": failed_dimensions,
        "watch_dimensions": watch_dimensions,
        "pass_floor": PASS_FLOOR,
        "watch_floor": WATCH_FLOOR,
        "required_floors": dimension_floors,
        "input_ref": input_ref,
        "input_identity": identity(state),
        "evaluated_state_identity": identity(payload["state"]),
        "state_projection_version": STATE_PROJECTION_VERSION,
        "request_bytes": len(canonical_json(payload).encode("utf-8")),
        "artifact_id": artifact.get("id"),
        "artifact_identity": identity(artifact["content"]),
        "model_requested": payload["model"],
        "model_returned": response.get("model"),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "answers": response["answers"],
        "usage": response.get("usage") if isinstance(response.get("usage"), dict) else None,
        "authority": "formal_gate",
    }


def build_bundle_receipt(bundle: str, state: Mapping[str, Any],
                         payload: Mapping[str, Any],
                         response: Mapping[str, Any], input_ref: str,
                         child_receipts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "newsletter-jev-gate-bundle-receipt/v1",
        "contract_version": CONTRACT_VERSION,
        "outcome_policy_version": OUTCOME_POLICY_VERSION,
        "state_projection_version": STATE_PROJECTION_VERSION,
        "bundle": bundle,
        "gates": list(GATE_BUNDLES[bundle]),
        "outcomes": {
            gate: receipt["outcome"] for gate, receipt in child_receipts.items()
        },
        "input_ref": input_ref,
        "input_identity": identity(state),
        "evaluated_state_identity": identity(payload["state"]),
        "request_bytes": len(canonical_json(payload).encode("utf-8")),
        "model_requested": payload["model"],
        "model_returned": response.get("model"),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "usage": response.get("usage") if isinstance(response.get("usage"), dict) else None,
        "authority": "formal_gate_bundle_accounting",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="以 TypeSafe JEV 執行電子報品質 Gate")
    parser.add_argument("gate", choices=tuple(GATES))
    parser.add_argument(
        "input", help="Gate input JSON；experience／sepia 可直接給稿件；使用 - 從 stdin 讀 JSON")
    parser.add_argument("--output", help="Receipt JSON 路徑；省略時輸出 stdout")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--dry-run", action="store_true",
                        help="只輸出 payload，不讀 key、不呼叫 JEV")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        state = load_state(args.input)
        if state.get("input_note") and args.gate not in {"experience", "sepia"}:
            raise ValueError(
                f"{args.gate} Gate 需要含 assignment、sources 與 artifact 的完整 JSON input")
        payload = build_payload(args.gate, state, args.model)
        result: Mapping[str, Any]
        if args.dry_run:
            result = payload
        else:
            response = validate_response(
                args.gate, call_jev(payload, timeout=args.timeout))
            result = build_receipt(args.gate, state, payload, response, args.input)
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
