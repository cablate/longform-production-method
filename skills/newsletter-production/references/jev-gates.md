# JEV 品質 Gate

電子報正式 Gate 由 TypeSafe JEV 執行。AI 負責準備輸入、寫作與回修，但不得自行宣告 Gate 通過；修訂後必須把新版本重新送入同一 Gate。

## 執行模型

每次 Gate 只處理一個確切版本：

1. AI 準備最小必要 JSON，包含稿件、內容類型、目前任務、該 Gate 必要的直接來源與公開邊界；腳本會再依 Gate allowlist 投影，未知的流程欄位不送入 JEV。
2. 執行 `scripts/newsletter_gate_jev.py <gate> input.json --output receipt.json`。正式 chain 維持每個 Gate 一次獨立 request；批次 request 目前只留在校準工具，不能產生正式通過證據。
3. 以每個 Gate 自己的 `receipt.outcome` 決定下一步；各原子答案全部保存，不挑最高單項當總評，也不讓同一 request 內其他 Gate 的結果互相抵銷。
4. `revise`、`refactor` 或 `recreate_candidate` 時，AI 只依本 Gate 的低信號面向回讀原文並修改；JEV 不負責生成文字。
5. 稿件、brief、來源或公開邊界改變後，舊 receipt 失效。

JEV 是正式 Gate 的判斷者。開發期案例比較可以幫助校準契約，但不能覆蓋正式 JEV Receipt。

## 七個固定 Gate

完整產製固定執行 `brief`、`truth`、`depth`、`experience`、`fidelity`、`prose` 與 `final`，沒有額外的全文潤稿分支。

| Gate | 使用時機 | 主要檢查 | 合法結果 |
|---|---|---|---|
| `brief` | 寫全文前 | 讀者任務、內容路線、來源支持、邊界、新增價值 | `pass`、`revise`、`recover_sources`、`author_only` |
| `truth` | 完整初稿後 | 事實、引句、因果、第一人稱、公開範圍 | `pass`、`revise`、`recover_sources`、`author_only` |
| `depth` | truth 通過後 | 承諾完成、來源容量、推理、路線特有價值、轉用邊界 | `pass`、`revise`、`recover_sources` |
| `experience` | depth 通過後 | 自然進入文章、背景、中斷承接、略讀路徑、必要術語、外部依賴與讀者自主 | `pass`、`revise` |
| `fidelity` | experience 通過後 | 作者主體、立場、第一人稱、敏感與重複 | `pass`、`revise`、`recover_sources`、`author_only` |
| `prose` | 目前版本、專案提供的 voice reference 與語言場域 | 套版、重複、句群與段落節奏、場域與聲音 | `pass`、`refactor`、`recreate_candidate` |
| `final` | 交作者前 | 確切版本、內外邊界、包裝一致、資產可用 | `pass`、`revise`、`author_only` |

## 輸入契約

輸入是 JSON object。至少提供：

```json
{
  "artifact": {
    "id": "weekly-example-v1",
    "content_type": "weekly_compilation",
    "content": "完整待審文字"
  },
  "assignment": {
    "reader_task": "讀者讀完要完成的理解",
    "target_content_type": "weekly_compilation 或 thematic_newsletter 等內容路線",
    "public_boundary": ["不可公開或不可外推的範圍"]
  },
  "sources": [
    {"locator": "source:example-001", "content": "實際支持內容"}
  ],
  "claim_source_map": [
    {
      "claim": "brief 中的一項承重主張",
      "support_kind": "direct 或 derived_from_multiple_direct_sources",
      "source_locators": ["source:example-001"]
    }
  ]
}
```

不要只送摘要。`assignment.target_content_type` 或 brief 本身必須讓 JEV 辨認這篇是深入文章、既有內容編選、短札記、通知、策展或其他路線；不能只寫「高品質文章」。`brief` 應為承重主張附上 `claim_source_map`，並區分直接支持與跨來源推導；同一張表必須一路帶進 `truth`、`depth` 與 `fidelity`。多主題週報尤其不能只給一大包來源，否則 Gate 必須重新猜測每個單元的支持關係。這三關同時必須包含足以核對的原文；`experience` 可另帶主旨、預覽與必要交付資訊，以檢查略讀路徑；`prose` 必須包含目前版本及可用的作者聲音依據；`final` 必須包含待交付的確切內容與必要資產／連結清單。

完整 chain 預設執行七次獨立 request：`brief`、`truth`、`depth`、`experience`、`fidelity`、`prose`、`final`。任一 Gate 不通過，AI 只按該 Gate 修稿；稿件一改，所有綁定舊 artifact identity 的內容 Gate Receipts 都失效，再從受影響的最早 Gate 重跑。若要批次呼叫，只能合併共用輸入的請求，不得合併判斷、平均結果或降低 Gate 要求。

## 回修規則

- 原子答案是必要條件的機率判斷，不以最高分或平均分取代總評。
- 正式路由通常沿用 JEV 的 `disposition`；但一致性護欄會拒絕兩種自相矛盾的總結：回傳 `pass` 卻有任一必要原子條件未達該面向具名門檻，以及回傳非 `pass` 卻沒有任何必要原子條件失敗。前者送回該 Gate 的最小修復路徑，後者改為帶 watch 的 `pass`。一般門檻 0.5 代表仍無法判定必要條件較可能成立，不能當作通過；具名 0.65 門檻只適用於下一條列出的研究承重面向。這不是取平均或挑最高分，而是讓有限 outcome 與全部必要條件保持邏輯一致。
- 一般必要面向在 `0.5 < noul < 0.65` 時記入非阻塞的 `watch_dimensions`。四個由研究確認的承重面向不允許以弱 watch 放行：`brief.content_route_fit`、`depth.route_specific_value_delivered`、`experience.skim_path_clear`、`experience.reader_autonomy_preserved` 必須高於 `0.65`；等於或低於門檻即回修。這是具名的 per-dimension floor，不把所有問題全面提高到同一分數，也不得為了追分無限重寫已通過版本。
- AI 回修時先找出與低信號面向對應的原句、來源與最小修改範圍，不把所有低信號都變成全文重寫。
- `recover_sources` 先補可查來源；無法取得時刪除、降格或縮小主張。
- `author_only` 只問一個不可替代的作者立場、本人經驗、公開決定或核准問題。
- `recreate_candidate` 另存候選，不覆蓋原稿；只有作者或責任編輯明示採用後才接回正式稿。
- 同一 Gate 連續兩次相同結果且沒有可指認改善時停止，留下 receipt 交作者或責任編輯決定，不降低標準硬過。

## Receipt

Receipt 至少保存 Gate 契約版本、outcome policy 版本、輸入雜湊、實際送審 state 雜湊、投影版本、稿件雜湊、JEV 模型、完成時間、完整 answers、JEV 原始 outcome、正式 outcome、failed／watch dimensions、一致性調整與 usage。批次模式的 usage 只記在 bundle receipt，child receipts 以 `usage_accounting` 指回它，避免把一次 request 重複計成多次成本。`pass` 只表示這個 Gate 對該確切版本通過；不等於作者核准、寄送或成效成立。

## 契約校準

Gate prompt 的「訓練」是版本化校準，不是修改模型權重：

1. 固定一份真實候選稿、完整來源與 brief。
2. 每個 Gate 建立一個只破壞該責任的 contrast case。
3. 同一契約先跑 reference 與 contrast，保存 input 與 receipt。
4. 只有出現誤殺、漏接、問題混合兩種責任或輸入契約不足時才改 prompt；沒有證據的 Gate 保持不動。
5. 用同一對案例重跑；reference 應通過或指出真缺陷，contrast 必須不通過。
6. 再用其他主題與內容類型做前瞻驗證；不得為了讓單一歷史稿全綠而降低必要條件。

批次 request 除了上述單關案例，還要驗證：reference bundle 內所有 Gate 都通過；每個針對性 contrast 至少被它所針對的 Gate 攔下；回傳缺少任何 prefixed question、錯型別或未知 choice 時整個 bundle 無效。相鄰 Gate 也可能因同一個真缺陷而合理失敗，這不算互相污染；真正禁止的是某 Gate 因其他 Gate 表現良好而通過。

契約變更後先執行 `python -m unittest discover -s tests -v`，再用 `examples/starter/article-state.json` 對受影響 Gate 執行 `--dry-run`。這只證明 payload 與本地契約成立，不取代正式產製時逐稿執行 `newsletter_gate_jev.py`，也不證明內容品質或作者接受。
