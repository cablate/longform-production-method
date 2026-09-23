# JEV Gates

本 Repo 使用 TypeSafe JEV 提供結構化語意判斷。所有 API 呼叫遵循目前官方 `POST https://api.typesafe.ai/v1/systemone` 契約；Key 由 `TYPESAFE_API_KEY` 提供。

## 選題判斷

| 判斷 | 負責什麼 | 不負責什麼 |
|---|---|---|
| `viability` | 候選是否有讀者問題、來源支持與足夠上下文 | 不決定發布優先級 |
| `relationship` | 與庫存內容是獨立、更新、合併、連回或已吸收 | 不以關鍵字相似代替讀者價值 |
| `destinations` | 三種非互斥格式是否具備內容條件 | 不決定本輪是否啟動 |
| `gap_route` | 缺口應查回、安全縮小、問作者或暫停 | 不替作者決定立場 |
| `plan_review` | 跨候選配置是否完整、獨立、安全且符合產能 | 不自動生成配置 |

## 文章 Gate

`brief → truth → depth → experience → fidelity → sepia → final`

每一關只收到判斷所需的最小 state projection。好讀不能抵銷事實錯誤，語氣自然也不能抵銷內容空洞。`final` 只接受綁定目前正文 identity 的前置 Receipt。

Noul 的機率接近 0.5 表示 yes/no 不確定，不是「中等程度」。Choice 的 confidence 描述機率分布集中程度，也不代表整個流程正確。門檻必須用自己的案例持續校準；Repo 內門檻是已使用過的預設值，不是所有領域的永久真理。

