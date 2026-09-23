# 來源契約

核心流程只接受標準來源包，不依賴任何特定平台、API 或資料庫。

每份素材應整理成一個 `source-packet/v1` JSON：

```json
{
  "schema_version": "source-packet/v1",
  "id": "source-001",
  "kind": "post",
  "title": "來源標題",
  "published_at": "2026-01-01T00:00:00Z",
  "content": "完整來源文字",
  "context": "理解這份來源所需的上下文",
  "provenance": {
    "locator": "https://example.com/or/local-id",
    "retrieved_at": "2026-01-02T00:00:00Z",
    "completeness": "complete"
  },
  "public_boundary": ["不得公開的內容或識別資訊"],
  "upstream_signals": {}
}
```

`upstream_signals` 可以保存來源平台已經完成的非互斥分析，例如內容特徵、證據密度、時效性或可能用途。它們是後續判斷的證據，不是發布排序，也不會由核心流程覆寫。

## 來源整理的責任

- 保留來源定位與取得時間。
- 取得作者的完整內容鏈，而不是只保留第一段。
- 將正文、補充、互動與不確定片段分開，避免偷偷拼接。
- 明示缺少的父文、回覆、附件或權限。
- 不把模型摘要冒充原始內容。
- 憑證只存在環境變數或外部秘密管理服務。

來源的原始格式與取得工具不屬於本方法論的責任。只要輸入符合相同契約，後續選題不應因來源平台而改變判斷標準。
