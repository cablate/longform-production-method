# Starter workspace

1. 填寫 `PROJECT.md` 的三個個人區塊。
2. 以 `sources/sample-source.json` 為格式加入自己的完整素材。
3. `inventory/content-index.json` 保存既有候選與已發布內容的索引。
4. `selection-inputs/` 與 `gate-inputs/` 是虛構的可執行範例，不是品質黃金答案。

範例只有一份小樣本來源，JEV 合理地可能回傳 `hold`、`needs_context` 或低信心結果。這正是流程要保留的訊號：不要為了讓展示通過而把來源不足改寫成確定結論。

正式執行產生的稿件放在 `drafts/`，JEV Receipt 放在 `receipts/<artifact-id>/<attempt>/`。兩者都應綁定確切內容 identity；正文改動後，舊 Receipt 只能作歷史證據。
