# 驗證與改善方法

檔案存在、測試通過或文字看起來像電子報，都不能單獨證明這套方法可靠。驗證必須分清楚契約是否正確、判斷是否穩定、成稿是否成立，以及真實作者是否接受。

## 四層證據

| 層次 | 要回答的問題 | 可用證據 | 不能宣稱 |
|---|---|---|---|
| 契約 | 檔案、schema、payload、choice、identity 與連結是否正確 | 單元測試、validator、dry-run | JEV 判斷正確、文章好看 |
| 判斷 | Gate 對參考與反例是否做出合理且穩定的有限判斷 | 固定案例、對照案例、正式 Receipt | 成稿已獲作者接受 |
| 成稿 | 來源、讀者任務、深度、聲音與交付包是否共同成立 | 完整來源、候選稿、七道 Gate、人工審讀 | 已發布或有成效 |
| 實際結果 | 作者投入、接受、寄送與讀者結果如何 | 真實往返、平台紀錄、成效資料 | 未觀察到的長期效果 |

只報告實際觀察到的層次。沒有作者往返，就把作者接受標成未驗證；沒有寄送證據，就不能說已發布或已送達。

## 每次修改怎麼驗證

1. 保存觸發修改的失敗案例與修改前結果。
2. 寫清楚希望改善什麼、哪些面向不能退步，以及停止條件。
3. 一次修改一個可辨認範圍。
4. 重跑直接受影響的案例，再選足以暴露非目標退步的對照案例。
5. 比較實際輸入、判斷、修稿範圍與輸出，不只比關鍵字或總分。
6. 新規則只有在多個不同案例成立、沒有明顯反例時，才升成穩定方法。

## 核心案例矩陣

1. **完整來源、零提問：**來源已含作者立場、公開邊界與必要上下文時，AI 不應重問已知資訊。
2. **來源不足、不捏造：**缺少不可替代的經驗、事實或權限時，應回查、縮小或停下；不得自行補第一人稱、引句或結果。
3. **多題與零題：**同一期間可能產生零到多個候選，不強迫選一個最高分題目。
4. **內容關係：**共用來源但讀者任務不同可獨立；已被既有內容實質吸收且沒有新增價值時，應合併、連回或暫不成篇。
5. **格式非互斥：**同一候選可同時適合週報、主題長文與短札記，但各自要有不同且完整的讀者任務。
6. **編選與深文分流：**多題週報不被硬湊成單一論點；判斷型深文必須展開證據、推理、限制與轉用邊界。
7. **事實與好讀不能互抵：**含來源錯誤但文筆流暢的版本仍應卡在 Truth；內容空洞但語氣自然的版本仍應卡在 Depth。
8. **作者保真：**作者的立場、確定程度、第一人稱與敏感邊界被削弱或改寫時，Fidelity 應要求修正。
9. **閱讀自主：**術語跳躍、依賴前文、沒有略讀路徑或用恐懼與假急迫逼迫行動時，Experience 應攔下。
10. **文字後製來回：**保留原稿與候選稿，確認 Prose 修改改善套版、重複或節奏時，沒有刪掉必要內容、改變作者意思或新增無來源敘述。
11. **版本失效：**正文的承重內容改變後，綁定舊 identity 的 Receipt 不能繼續當作通過證據。
12. **乾淨交付：**正文不得混入提示詞、Receipt、待辦、內部審查狀態或私人來源；Final 通過仍只代表可交作者審閱。
13. **局部修改：**只改局部時，從第一個受影響的 Gate 重跑；不因方法完整就擴張成整期重製。
14. **停止條件：**連續兩輪定點修正沒有可辨認改善時停止，保留 blocker，不降低標準硬過。

## JEV 契約檢查

七道 Gate：`brief`、`truth`、`depth`、`experience`、`fidelity`、`prose`、`final`，都必須：

- 建立符合官方介面的 typed payload。
- 拒絕缺題、錯型別、未知 choice 與越界 noul。
- 只接收自己的最小 state projection。
- 保存 model、輸入 identity、完成時間、原子答案與正式 outcome。
- 在 required dimension 未達門檻時，不得產生互相矛盾的 pass Receipt。

直接 Markdown 只適用於不依賴外部來源的 `experience` 與 `prose`；其他 Gate 必須收到含任務、來源與必要對照的 JSON state。

## Repository 變更的最小檢查

```powershell
python -m unittest discover -s tests -v
python scripts/validate_workspace.py examples/starter --allow-placeholders
python skills/newsletter-production/scripts/topic_selection_jev.py viability examples/starter/selection-inputs/viability.json --dry-run
python skills/newsletter-production/scripts/newsletter_gate_jev.py truth examples/starter/gate-inputs/article-state.json --dry-run
```

另外檢查 Markdown 相對連結、範例是否完全虛構、是否誤納私人來源／草稿／Receipt／本機狀態，以及文件是否引用不存在的腳本或未隨 Repo 提供的必要依賴。

## 回報狀態

- `completed`：宣告範圍內的檢查有直接證據且沒有未解硬失敗。
- `needs_user`：只剩作者才能決定的立場、公開邊界或確切版本接受。
- `degraded`：可交付部分結果，但有明確依賴或檢查無法完成。
- `unverified`：目前只有較低層證據，不能推論到更高層行為。
