# Longform Production Method

一套把零散真實素材發展成週報、電子報與其他長文作品的方法，以及一份可執行的最小參考實作。

它處理的不是「叫 AI 寫長一點」，而是三個更難的問題：

- 一批素材裡其實有幾個值得發展的題目？
- 每個題目適合成為週報單元、主題長文、短札記，還是先留在庫存？
- AI 寫出的文章，如何經過可追溯的分段檢查，而不是靠同一個模型說自己寫得很好？

本方法把工作分給三種角色：AI 負責理解、組合、寫作與定點回修；TypeSafe JEV 負責事先定義的有限品質判斷；作者或責任編輯保留立場、公開邊界、優先順序與最終核准。Repo 內的 Python 腳本只實作資料契約、JEV 呼叫與 Receipt，不替代內容判斷。

它不是內容平台整合包，也不是通用工作流引擎。來源的原始格式與取得工具由使用者自行決定；本方法只規定進入選題時必須具備的素材、上下文與來源定位。

## 你需要提供三件事

1. **素材來源**：這批內容從哪裡來、範圍到哪裡、哪些可以公開。
2. **取得方式**：如何取得完整內容並整理成可追溯的來源包。
3. **作者與讀者**：作者能負責的立場與聲音依據，以及這篇內容要幫讀者完成什麼理解或判斷。

選題方法、內容路線、JEV 問題、七道文章 Gate、退回條件與 Receipt 規則都已經提供，不要求使用者重新設計。

## 方法全貌

### 1. 素材進入內容庫存

```text
驗收來源完整度與公開邊界
→ 從全部素材發現零到多個候選題目
→ 判斷候選是否成立
→ 與既有內容比較
→ 保存獨立、更新、合併、連回或已吸收的關係
```

選題不是挑一個最高分，也不只看最新一批素材。它先建立可持續使用的內容庫存。

### 2. 內容庫存形成生產配置

```text
讀取目前可用候選
→ 分別判斷週報、主題長文與短札記的格式準備度
→ AI 依時效、差異與產能提出整體配置
→ JEV 檢查遺漏、重複、跨篇依賴、來源邊界與過載
→ 作者或責任編輯一次確認
```

同一題可以適合多種格式，但每份作品必須完成不同且可獨立理解的讀者任務。

### 3. 正式長文產製

```text
Assignment
→ Brief → JEV Brief Gate
→ 完整初稿
→ Truth
→ Depth
→ Experience
→ Fidelity
→ Prose
→ Final
→ 作者核准
```

七道文章 Gate 各自把關不同責任：

| Gate | 把關內容 |
|---|---|
| Brief | 讀者任務、內容路線、來源支持、範圍與新增價值 |
| Truth | 事實、引句、因果、第一人稱與公開安全 |
| Depth | 文章承諾、來源容量、推理、路線特有價值與適用邊界 |
| Experience | 入口、背景、導航、略讀路徑、術語負擔與讀者自主 |
| Fidelity | 作者主體、立場、第一人稱、敏感內容與是否只是換字改寫 |
| Prose | 套版、重複、句群、段落節奏、場域與作者聲音 |
| Final | 確切版本、前置 Receipt、交付包與幕後資料外漏 |

Gate 失敗時，AI 只修改受影響的位置，再用新內容重跑同一關。來源錯誤不能被好讀抵銷，內容空洞也不能用自然語氣掩蓋。

## 為什麼使用 JEV

JEV 不負責寫文章，也不替作者決定要發布什麼。它把「這項條件是否成立」或「目前應走哪個有限處置」轉成程式可保存的 typed judgment。

這讓流程能夠：

- 保存每次判斷看到的確切 state。
- 分開不同品質責任，避免優點互相抵銷缺陷。
- 在正文改動後讓舊 Receipt 失效。
- 保留不確定性，而不是把單一分數當成真理。
- 用案例持續校準問題與門檻。

正式執行需要 `TYPESAFE_API_KEY`。沒有 Key 時可以用 `--dry-run` 檢查將送出的 state 與 questions，但不能宣稱 Gate 已通過。

## 開始使用

需求：Python 3.11+。腳本只使用 Python 標準函式庫。

```powershell
git clone https://github.com/cablate/longform-production-method.git
cd longform-production-method
python scripts/bootstrap_workspace.py my-publication
```

填寫 `my-publication/PROJECT.md` 的三個區塊並加入來源包後，在支援 [Agent Skills](https://agentskills.io/) 的環境安裝本方法：

```powershell
npx skills add cablate/longform-production-method --skill newsletter-production
```

接著交代 Agent：

> 請使用 newsletter-production Skill，讀取 my-publication/PROJECT.md 與 sources，完整執行選題；先交內容配置，確認後再產製所有標為 start 的長文。

正式執行或檢查 JEV 輸入：

```powershell
$env:TYPESAFE_API_KEY = "your-key"

# 選題判斷
python skills/newsletter-production/scripts/topic_selection_jev.py viability input.json --output receipt.json

# 文章品質 Gate
python skills/newsletter-production/scripts/newsletter_gate_jev.py truth article-state.json --output receipt.json

# 不呼叫 API，只檢查 payload
python skills/newsletter-production/scripts/newsletter_gate_jev.py truth examples/starter/gate-inputs/article-state.json --dry-run

# 檢查起始工作區與私人資料邊界
python scripts/validate_workspace.py examples/starter --allow-placeholders
```

`examples/starter/` 提供完全虛構的來源包、候選輸入與文章 Gate 輸入。範例不是品質黃金答案；低信心或暫緩結果同樣是應保留的有效訊號。

## 怎麼讀這個 Repository

- 想先理解方法：讀[方法總覽](docs/method.md)。
- 要準備自己的素材：讀[來源契約](docs/source-contract.md)，再複製 `examples/starter/`。
- 要讓 Agent 正式執行：以 `skills/newsletter-production/SKILL.md` 為唯一方法入口。
- 要調整判斷：讀[JEV Gates](docs/gates.md)與其指向的正式契約。

讀者文件負責說明；Skill 與它直接引用的 references 才是執行依據，避免兩套規則各自演進。

## Repository 內容

```text
skills/newsletter-production/   Agent Skill、完整方法與 JEV 判斷腳本
docs/                           給使用者閱讀的方法、來源與 Gate 導覽
schemas/                        來源包公開格式
examples/starter/               不含私人內容的起始工作區
scripts/                        建立與驗證工作區
tests/                          不呼叫外部 API 的契約測試
```

## 不可破壞的邊界

- 分開來源事實、作者已表達內容、AI 推論與待確認缺口。
- 不捏造第一人稱經驗、引句、結果、因果、權限或作者聲音。
- 所有正式 JEV Receipt 綁定確切輸入 identity；正文改動後不得沿用舊通過結果。
- Gate 通過最多表示可以交作者審閱，不等於作者核准或已發布。
- 不自動寄送、不自動公開，也不把 API Key 寫入 Repository。

深入閱讀：[方法總覽](docs/method.md) · [來源契約](docs/source-contract.md) · [JEV Gates](docs/gates.md)

## License

[MIT](LICENSE)
