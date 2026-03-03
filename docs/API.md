# 智能纪要 API 参考

所有 v1 端点列表（含独立查询、映射、专有名词、Chunk-主题匹配）。

---

## 一、核心接口

### POST /api/v1/smart-minutes/generate

生成纪要，一次性返回。

**请求体**：`MinutesRequest`（见 [USAGE.md](USAGE.md#二请求与响应)）

**响应**：`MinutesResponse`（`minutes_content`、`references`、`structured_output`、`warnings` 等）

### POST /api/v1/smart-minutes/generate-stream

流式生成纪要，SSE 协议。

**请求体**：同 `MinutesRequest`

**响应**：`text/event-stream`，包含阶段事件与正文 token

### POST /api/v1/smart-minutes/retrieve

仅检索，不调用 LLM。

**请求体**：同 `MinutesRequest`

**响应**：`MinutesResponse`（`minutes_content` 为空，`references`、`mapped_terms`、`resolved_speakers` 有值）

### POST /api/v1/smart-minutes/ingest-from-md

MD 文件入库 Milvus。

**请求体**：
```json
{"kb_name": "product_docs", "file_name": "requirements", "collection_name": "minutes"}
```

**响应**：`{"success": bool, "ingested_count": int, "errors": [], "deleted_count": int}`

---

## 二、独立查询 API（仅检索，不调 LLM）

所有查询接口均支持 `kb_name` 或 `collection_name` 指定 Milvus 集合。

### POST /api/v1/smart-minutes/query/series

同系列历史纪要。

**请求体**：
```json
{"meeting_type": "周会", "meeting_name": "产品周会", "top_k": 5, "kb_name": "minutes"}
```

**响应**：`{"items": [...], "collection": "..."}`

### POST /api/v1/smart-minutes/query/by-topic

议题/相似议题历史。

**请求体**：
```json
{"topic_name": "需求评审", "top_k": 5, "kb_name": "minutes"}
```

### POST /api/v1/smart-minutes/query/by-person

按人查询。若口头称呼对应多人，返回 `formal_names` 供澄清。

**请求体**：
```json
{"person_name": "老张", "top_k": 5, "kb_name": "minutes"}
```

**响应**：`{"items": [...], "collection": "..."}` 或 `{"oral_name": "...", "formal_names": [...], "ambiguous": true}`

### POST /api/v1/smart-minutes/query/attachments

附件信息。

**请求体**：
```json
{"meeting_type": "周会", "meeting_name": "产品周会", "kb_name": "minutes"}
```

### POST /api/v1/smart-minutes/query/topic-from-draft

口水稿→议题名。

**请求体**：
```json
{"draft_text": "今天先过需求评审...", "top_k": 5, "kb_name": "minutes"}
```

### POST /api/v1/smart-minutes/query/similar-todos-issues

类似待办/遗留。

**请求体**：
```json
{"todos_or_issues": ["完成测试用例编写"], "top_k": 5, "kb_name": "minutes"}
```

### POST /api/v1/smart-minutes/query/similar-conclusions

类似议题结论。

**请求体**：
```json
{"conclusions": ["本周冻结需求范围"], "top_k": 5, "kb_name": "minutes"}
```

---

## 三、映射与扩展

### POST /api/v1/smart-minutes/mappings/oral-names

批量添加或更新口头称呼→正式人名映射。

**请求体**：
```json
{"mappings": [{"oral_name": "老张", "formal_name": "张三", "employee_id": "E001"}]}
```

**响应**：`{"success_count": int, "failed_count": int}`

### POST /api/v1/smart-minutes/match-chunks-to-topics

Chunk-主题匹配。

**请求体**：
```json
{"chunks": [{"chunk_id": "c1", "text": "..."}], "topics": ["需求评审", "进度同步"], "unclassified_label": "未分类"}
```

**响应**：`{"assignments": [{"chunk_id": "c1", "topic": "需求评审"}]}`

### POST /api/v1/smart-minutes/extract-proper-nouns

从文本或 chunks 提取专有名词并写入存储。

**请求体**：
```json
{"kb_name": "product_docs", "text": "会议讨论了 Alpha 项目...", "file_name": "meeting_001.md"}
```

**响应**：`{"success": bool, "added": int, "error": "..."}`

### GET /api/v1/smart-minutes/proper-nouns

按知识库查询专有名词列表。

**参数**：`kb_name`（必填）、`collection_name`、`page`、`page_size`

**响应**：`{"items": [...], "total": int, "page": int, "page_size": int}`

---

## 四、Schema 管理（内部）

- `GET /api/v1/schema/info/{collection_name}`：Schema 信息
- `POST /api/v1/schema/register-field`：注册扩展字段
- `GET /api/v1/schema/registered-fields`：已注册字段
- `DELETE /api/v1/schema/register-field/{field_name}`：注销字段
- `POST /api/v1/schema/generate-fields`：为存量数据生成字段
- `POST /api/v1/schema/migrate`：迁移 Collection
- `POST /api/v1/schema/preview-field-generation`：预览字段生成

---

## 五、健康检查

- `GET /health`：返回 `{"status": "ok"}`
