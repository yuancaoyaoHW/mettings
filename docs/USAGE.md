# 智能纪要使用指南

面向使用智能纪要**生成会议纪要**或**仅做检索**的调用方。

---

## 一、快速开始

### 1.1 安装与启动 API

```bash
# 克隆或进入项目目录
cd mettings

# 虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

# 安装依赖
pip install -r requirements.txt

# 按需配置 .env（见下方环境变量）
# 启动服务
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

服务启动后：

- 健康检查：`GET http://localhost:8000/health`
- 生成纪要：`POST http://localhost:8000/api/v1/smart-minutes/generate`
- 流式生成：`POST http://localhost:8000/api/v1/smart-minutes/generate-stream`
- 仅检索：`POST http://localhost:8000/api/v1/smart-minutes/retrieve`
- MD 入库：`POST http://localhost:8000/api/v1/smart-minutes/ingest-from-md`

### 1.2 Python 进程内调用

```python
from smart_minutes import SmartMinutesService, MinutesRequest, MinutesResponse
from smart_minutes.adapters.mapping_store import MappingStoreAdapter
from smart_minutes.adapters.retrieval import RetrievalAdapter
from smart_minutes.adapters.speaker_resolver import SpeakerResolverAdapter

# 使用 stub 适配器（无真实 Milvus 时检索结果为空）
retrieval = RetrievalAdapter(client=None, collection_name="")
mapping = MappingStoreAdapter(initial_oral_map={"老张": "张三"})
speaker = SpeakerResolverAdapter()
service = SmartMinutesService(retrieval, mapping, speaker)

req = MinutesRequest(
    meeting_name="产品周会",
    topics=["需求评审", "进度同步"],
    oral_names=["老张"],
)
resp = service.run(req)
print(resp.minutes_content)
print(resp.mapped_terms)   # 口头→人名解析结果
print(resp.references)     # 检索到的参考片段
```

### 1.3 生产接入（真实 Milvus + MySQL 映射）

```python
import os
from smart_minutes import SmartMinutesService
from smart_minutes.adapters.retrieval import create_retrieval_adapter
from smart_minutes.adapters.mapping_store import MappingStoreAdapter
from smart_minutes.adapters.speaker_resolver import SpeakerResolverAdapter
from smart_minutes.adapters.stores.mapping_mysql import create_mapping_store_from_env

retrieval = create_retrieval_adapter(
    collection_name=os.getenv("MILVUS_COLLECTION_NAME", ""),
    milvus_uri=os.getenv("MILVUS_URI"),
    token=os.getenv("MILVUS_TOKEN", ""),
    db_name=os.getenv("MILVUS_DB_NAME", "default"),
)
mapping = create_mapping_store_from_env() or MappingStoreAdapter(initial_oral_map={})
speaker = SpeakerResolverAdapter()
service = SmartMinutesService(retrieval, mapping, speaker)
```

说明：

- 优先使用 `MAPPING_DB_URI`；
- 若未配置 `MAPPING_DB_URI`，会回退读取 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`；
- 若 MySQL 映射未配置，可回退到内存映射（`MappingStoreAdapter`）。

---

## 二、请求与响应

### 2.1 请求体（MinutesRequest）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| meeting_type | string | 否 | 会议类型 |
| meeting_name | string | 否 | 会议名称 |
| project | string | 否 | 项目标识（同系列加权过滤） |
| department | string | 否 | 部门标识（同系列加权过滤） |
| organization | string | 否 | 组织标识（同系列加权过滤） |
| venue_name | string | 否 | 会场名称 |
| meeting_id | string | 否 | 会议 ID（已持久化时可传） |
| topics | string[] | 否 | 议题列表 |
| person_names | string[] | 否 | 人名（正式名） |
| oral_names | string[] | 否 | 口头称呼（会查映射表转正式名） |
| draft_text | string | 否 | 本次会议口水稿全文 |
| draft_segments_by_topic | object | 否 | 已按议题切好的口水稿 `{ "议题名": "内容" }` |
| realtime_speaker | object | 否 | 当前片段发言人识别结果，见下表 |
| open_issues | string[] | 否 | 待办/遗留片段（用于查相似历史） |
| conclusions | string[] | 否 | 议题结论片段（用于查相似历史） |
| options | object | 否 | 扩展项，如 `{ "top_k": 5 }` |

`options` 还支持分类型检索权重（用于 `todo/open_issue/conclusion`）：

```json
{
  "top_k": 5,
  "retrieval_weights": {
    "todo": { "type_weight": 0.8, "dense_weight": 0.6, "sparse_weight": 0.4 },
    "open_issue": { "type_weight": 1.4, "dense_weight": 0.7, "sparse_weight": 0.3 },
    "conclusion": { "type_weight": 1.2, "dense_weight": 0.65, "sparse_weight": 0.35 }
  }
}
```

当配置了会议类型模板（见环境变量 `SMART_MINUTES_TEMPLATES_PATH` / `SMART_MINUTES_TEMPLATES_JSON`）后，
若请求里提供 `meeting_type`，系统会按 `meeting_type` 自动套用默认 `top_k` 和分类型权重。
参数优先级为：**请求 options > meeting_type 模板 > 全局默认值**。

**realtime_speaker**：

| 字段 | 类型 | 说明 |
|------|------|------|
| face_result | any | 人脸识别结果（如 `{ "name": "张三", "confidence": 0.9 }`） |
| voice_result | any | 声纹/说话人识别结果 |
| venue_name | string | 会场名称 |

### 2.2 响应体（MinutesResponse）

| 字段 | 类型 | 说明 |
|------|------|------|
| minutes_content | string | 生成的纪要正文（仅检索时为空） |
| references | array | 参考片段列表，每项含 pk、score、page_content、source、topic、author、time 等 |
| resolved_speakers | string[] | 本场解析出的发言人正式名 |
| speaker_resolutions | array | 发言人融合结果（resolved_name、confidence、candidates、status） |
| mapped_terms | string[] | 本场用到的专业词（或口头→人名解析结果） |
| structured_output | object | 结构化纪要输出（meeting_info、topics、materials、traceability） |
| errors | array | 错误列表，每项含 code、message |
| warnings | string[] | 告警信息（如某路检索为空） |
| partial | boolean | 是否部分成功（有未完成项时为 true） |

### 2.3 请求示例（JSON）

**生成纪要：**

```json
{
  "meeting_name": "产品周会",
  "meeting_type": "周会",
  "topics": ["需求评审", "进度同步"],
  "oral_names": ["老张", "李工"],
  "draft_text": "老张说需求已经评审完了，李工这边下周能上线。",
  "open_issues": ["跟进测试环境部署"],
  "options": { "top_k": 5 }
}
```

**仅检索（不生成正文）：**
 
```json
{
  "meeting_name": "产品周会",
  "topics": ["需求评审"],
  "person_names": ["张三"]
}
```

调用 **POST /api/v1/smart-minutes/retrieve** 时请求体同上；响应中 `minutes_content` 为空，`references`、`mapped_terms`、`resolved_speakers` 为检索与映射结果。

**流式调用（SSE）：**

```bash
curl -N -X POST "http://localhost:8000/api/v1/smart-minutes/generate-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "meeting_name": "周例会",
    "topics": ["进度同步"],
    "oral_names": ["老张"]
  }'
```

你会先收到 JSON 格式的阶段事件，再收到 OpenAI 格式的 token 流，最后收到 `[DONE]`。

---

## 三、环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| MILVUS_URI | Milvus 连接地址 | `http://localhost:19530` |
| MILVUS_TOKEN | Milvus 认证 token | - |
| MILVUS_DB_NAME | 数据库名 | `default` |
| MILVUS_COLLECTION_NAME | 集合名 | `minutes` |
| EMBEDDING_BASE_URL | Embedding 服务地址 | - |
| EMBEDDING_MODEL_NAME | 模型名 | - |
| LLM_API_KEY | LLM 密钥 | - |
| LLM_BASE_URL | LLM 服务地址 | - |
| LLM_MODEL_NAME | 模型名 | - |
| CONTEXT_TOKEN_BUDGET | 单次上下文 token 上限 | 8000 |
| DEFAULT_TOP_K | 默认召回条数 | 5 |
| SMART_MINUTES_TEMPLATES_PATH | 会议类型模板文件路径（JSON/YAML） | `config/templates.json` |
| SMART_MINUTES_TEMPLATES_JSON | 会议类型模板 JSON 字符串（可选） | `{"周会":{"top_k":3}}` |
| MAPPING_DB_URI | 映射表 DB（可选） | `mysql://user:pass@host/db` |
| FILE_PATH | MD 文件存放路径 | `./data/files` |

更多见项目根目录 `.env.example`。

---

## 四、能力与输入对应关系

| 你提供的输入 | 模块会做的事 |
|--------------|----------------|
| 会议类型/名称 | 查同系列最新历史纪要作模板、相关附件与专业词 |
| 议题名称 | 查同/似议题历史（总结、遗留）、在附件中搜关键信息、按议题切口水稿 |
| 人名/口头称呼 | 口头→正式名映射、查该人相关历史纪要 |
| 口水稿全文 + 议题 | 按议题分割口水稿；用口水稿查相似历史议题名 |
| 待办/遗留/结论片段 | 按 `todo/open_issue/conclusion` 分类型召回，支持权重调参 |
| 人脸/声纹/会场 | 融合为当前发言人正式名 |

---

## 五、常见问题

**Q：返回的 minutes_content 是占位文案？**  
A：当前默认未接 LLM，仅为占位。对接真实 LLM 后会在门面内调用生成正文。

**Q：references 为空？**  
A：未注入真实 Milvus 客户端或集合无数据时，检索结果为空。请按《对接手册》注入 `RetrievalAdapter` 并配置正确集合。

**Q：如何只做「口头→人名」或「会议类型→专业词」？**  
A：调用 **POST /api/v1/smart-minutes/retrieve**，请求中只填 `oral_names` 或 `meeting_type`/`meeting_name`，看响应中的 `mapped_terms`。

**Q：partial 为 true 时怎么处理？**  
A：表示部分步骤失败或未命中，可查看 `warnings` 列表；已生成的内容和 `references` 仍可使用，可按需降级展示或重试。

---

## 六、扩展字段与 Schema 管理

系统支持为 Milvus 数据动态生成扩展字段，利用 LLM 能力自动分析内容。

### 6.1 内置扩展字段

入库时自动生成的字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `summary_short` | string | 短摘要（50字） |
| `summary_detailed` | string | 详细摘要（200字） |
| `keywords` | array | 关键词（最多5个） |
| `sentiment` | string | 情感倾向（positive/negative/neutral） |
| `importance` | int | 重要性评分（1-5） |
| `category` | string | 业务分类 |
| `action_items_structured` | array | 结构化行动项 |
| `decision_summary` | string | 决策结论提取 |

### 6.2 自定义扩展字段

通过 Schema 管理接口注册自定义字段：

```python
from smart_minutes import SmartMinutesService

service = SmartMinutesService(...)

# 注册扩展字段
service.register_extension_field({
    "field_name": "my_custom_field",
    "field_type": "string",
    "description": "自定义字段描述",
    "generation_method": "llm",  # llm / rule / none
    "generation_prompt": "请从以下内容中提取..."
})
```

### 6.3 Schema 管理接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/schema/info/{collection_name}` | GET | 获取 Schema 信息 |
| `/api/v1/schema/register` | POST | 注册扩展字段 |
| `/api/v1/schema/list` | GET | 列出已注册字段 |
| `/api/v1/schema/unregister` | POST | 注销扩展字段 |
| `/api/v1/schema/generate` | POST | 为存量数据生成字段 |
| `/api/v1/schema/migrate` | POST | 迁移到动态字段 Collection |
| `/api/v1/schema/preview` | POST | 预览字段生成效果 |

---

## 七、MD 文件入库

系统支持将 Markdown 文件解析为 chunk 后入库 Milvus，便于历史文档的检索和引用。

### 7.1 接口说明

**POST /api/v1/smart-minutes/ingest-from-md**

将指定路径下的 MD 文件解析、分块、向量化后存入 Milvus。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| kb_name | string | 是 | 知识库名（对应文件夹） |
| file_name | string | 是 | 文档名（对应子文件夹） |
| collection_name | string | 否 | 集合名，默认使用环境变量配置 |

**响应体：**

| 字段 | 类型 | 说明 |
|------|------|------|
| success | boolean | 是否成功 |
| ingested_count | int | 入库的 chunk 数量 |
| errors | string[] | 错误信息列表 |
| deleted_count | int | 删除的旧数据数量 |

### 7.2 使用示例

```bash
# 将 {FILE_PATH}/product_docs/requirements/v1.md 入库
curl -X POST "http://localhost:8000/api/v1/smart-minutes/ingest-from-md" \
  -H "Content-Type: application/json" \
  -d '{
    "kb_name": "product_docs",
    "file_name": "requirements",
    "collection_name": "minutes"
  }'
```

### 7.3 Python 调用

```python
from smart_minutes import create_service

service = create_service()

# 入库 MD 文件
result = service.ingest_from_md(
    kb_name="product_docs",
    file_name="requirements",
    collection_name="minutes"
)

print(f"入库成功: {result['success']}")
print(f"入库数量: {result['ingested_count']}")
```

### 7.4 文件路径结构

MD 文件存放路径结构：

```
{FILE_PATH}/
  ├── {kb_name}/
  │   ├── {file_name}/
  │   │   └── vlm/
  │   │       └── *.md
  │   └── ...
  └── ...
```

例如，设置 `FILE_PATH=./data/files`，则文件应存放于：
- `./data/files/product_docs/requirements/vlm/document.md`

### 7.5 入库流程

1. **读取文件**：从指定路径读取所有 `.md` 文件
2. **解析内容**：提取文本内容和元数据
3. **分块处理**：按段落/标题切分为 chunk
4. **向量化**：调用 Embedding 服务生成向量
5. **生成扩展字段**：使用 LLM 生成 summary、keywords 等
6. **删除旧数据**：根据 source_id 删除该文档的历史数据
7. **插入新数据**：将 chunk 和向量写入 Milvus

### 7.6 注意事项

- 需要配置 `FILE_PATH` 环境变量指定文件存放根目录
- 需要配置 `MILVUS_COLLECTION_NAME` 指定默认集合
- 入库前会自动删除该文档的历史数据（全量替换）
- 支持动态字段，可自动入库扩展字段
