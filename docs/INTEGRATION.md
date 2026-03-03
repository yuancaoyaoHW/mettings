# 智能纪要对接手册

面向将智能纪要作为**独立模块**接入会议应用、OA、录制服务等场景的开发者。

---

## 一、对接方式概览

| 方式 | 适用场景 | 依赖 |
|------|----------|------|
| **进程内** | 同一 Python 进程，直接 `import` 调用 | 注入 IRetrieval、IMappingStore、ISpeakerResolver |
| **HTTP** | 跨进程/跨语言，通过 REST 调用 | 部署 `api/main.py`，请求/响应为 JSON |

### 1.1 执行流程图

```mermaid
flowchart TD
  A[外部请求 MinutesRequest] --> B[SmartMinutesService / API 门面]
  B --> C[Router 生成工具建议]
  C --> D[MinutesAgent 执行工具]

  D --> E1[Group1 顺序: 映射/专业词]
  D --> E2[Group2 并行: RAG/附件检索]
  D --> E3[Group3 顺序: 口水稿分割/发言人融合]

  E1 --> F[汇总 references/mapped_terms/speakers]
  E2 --> F
  E3 --> F

  F --> G[组装上下文 context]
  G --> H[按预算裁剪 <= context_token_budget]
  H --> I[调用 LLM 生成纪要]

  I --> J{是否生成成功}
  J -- 是 --> K[返回 MinutesResponse<br/>minutes_content + references]
  J -- 否 --> L[降级返回占位内容 + errors/warnings]
```

### 1.2 组件架构图

```mermaid
flowchart LR
  subgraph External[调用方 / 外部系统]
    X1[会议应用]
    X2[OA/审批]
    X3[录制转写服务]
  end

  subgraph SmartMinutes[smart_minutes 模块]
    A[api.py 门面 SmartMinutesService]
    B[agents/router.py]
    C[agents/minutes_agent.py]
    D[tools/*]
    E[contracts.py 抽象接口]
    A --> B
    A --> C
    B --> C
    C --> D
    C -.依赖抽象.-> E
  end

  subgraph Infra[可替换基础设施]
    R[RetrievalAdapter<br/>Milvus/Hybrid Client]
    M[MappingStoreAdapter<br/>MySQL/配置映射]
    S[SpeakerResolverAdapter<br/>人脸/声纹/会场]
    LLM[services/llm.py]
    EMB[services/embedding.py]
    ING[pipelines/ingest.py]
  end

  X1 --> A
  X2 --> A
  X3 --> A

  E --> R
  E --> M
  E --> S
  C --> LLM
  D --> EMB
  ING --> EMB
```

---

## 二、进程内对接

### 2.1 依赖的抽象接口

模块只依赖三个抽象（定义在 `smart_minutes.contracts`），由**调用方**提供实现并注入：

| 接口 | 职责 | 必须实现的方法 |
|------|------|----------------|
| **IRetrieval** | 向量/混合检索 | `search(query_text, *, topic_filter, source_filter, level1_filter, author_filter, type_filter, top_k) -> List[dict]` |
| **IMappingStore** | 口头→人名、会议类型→专业词 | `resolve_oral_to_formal(oral_name) -> Optional[str]`<br>`get_professional_terms(meeting_type, meeting_name) -> List[str]` |
| **ISpeakerResolver** | 人脸/声纹/会场 → 发言人 | `resolve_speaker(face_result, voice_result, venue_name) -> Optional[SpeakerResolution]`（可选） |

返回的 `dict` 建议包含：`pk`, `score`, `page_content`, `source`, `level1`, `level2`, `author`, `time`, `version`, `topic`，以及可追溯字段 `source_id`, `source_position`, `confidence`。

### 2.2 使用本仓库自带的适配器

若使用现有 Milvus 混合检索客户端，可用 `RetrievalAdapter` 包装：

```python
from smart_minutes import SmartMinutesService, MinutesRequest, MinutesResponse
from smart_minutes.adapters.retrieval import RetrievalAdapter
from smart_minutes.adapters.mapping_store import MappingStoreAdapter
from smart_minutes.adapters.speaker_resolver import SpeakerResolverAdapter

# 假设已有 MilvusHybridClient，且 search 支持 filter=expr
milvus_client = ...  # 你的 MilvusHybridClient 实例
retrieval = RetrievalAdapter(client=milvus_client, collection_name="your_collection")
mapping = MappingStoreAdapter(initial_oral_map={"老张": "张三"})  # 或从 DB 加载
speaker = SpeakerResolverAdapter()  # 或接入真人脸/声纹 API

service = SmartMinutesService(retrieval, mapping, speaker)
request = MinutesRequest(meeting_name="周例会", topics=["进度同步"], oral_names=["老张"])
response = service.run(request)
print(response.minutes_content)
print(response.references)
```

### 2.3 自定义实现注入

实现 Protocol 即可，无需继承：

```python
class MyRetrieval:
    def search(self, query_text, *, topic_filter=None, source_filter=None, level1_filter=None,
               author_filter=None, type_filter=None, top_k=5, **kwargs):
        # 调用你的向量库，返回 [{"pk": ..., "score": ..., "page_content": ..., ...}]
        return []

service = SmartMinutesService(MyRetrieval(), my_mapping, my_speaker)
```

### 2.4 配置

- 集合名、top_k、上下文预算等可通过 `SmartMinutesConfig` 传入，或由环境变量提供（见 `.env.example`）。
- `SmartMinutesService(..., config=SmartMinutesConfig(collection_name="xx", context_token_budget=8000))`
- 支持按 `meeting_type` 自动套用策略模板（`top_k`、`todo/open_issue/conclusion` 权重等）：
  - `SMART_MINUTES_TEMPLATES_PATH`：模板文件路径（JSON/YAML）
  - `SMART_MINUTES_TEMPLATES_JSON`：模板 JSON 字符串（可选，未设置文件路径时生效）
  - 参数优先级：**请求 options > meeting_type 模板 > 全局默认值**

---

## 三、HTTP 对接

### 3.1 启动服务

```bash
cd /path/to/mettings
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 3.2 生产环境注入真实实现

`api/main.py` 会先尝试按环境变量创建真实适配器（Milvus/MySQL）；若未提供配置则回退到 stub 适配器。生产环境也可在应用启动时显式注入真实实现：

- 检索：`create_retrieval_adapter(...)`（或你自己的 `IRetrieval` 实现）
- 映射：`create_mapping_store_from_env()`（优先读取 `MAPPING_DB_URI`，也支持 `MYSQL_*`）
- 发言人：`SpeakerResolverAdapter`（或你自己的 `ISpeakerResolver`）

示例（lifespan 初始化）：

```python
import os
from smart_minutes import SmartMinutesService
from smart_minutes.adapters.retrieval import create_retrieval_adapter
from smart_minutes.adapters.mapping_store import MappingStoreAdapter
from smart_minutes.adapters.speaker_resolver import SpeakerResolverAdapter
from smart_minutes.adapters.stores.mapping_mysql import create_mapping_store_from_env

collection_name = os.getenv("MILVUS_COLLECTION_NAME", "")
retrieval = create_retrieval_adapter(
    collection_name=collection_name,
    milvus_uri=os.getenv("MILVUS_URI"),
    token=os.getenv("MILVUS_TOKEN", ""),
    db_name=os.getenv("MILVUS_DB_NAME", "default"),
)
mapping = create_mapping_store_from_env() or MappingStoreAdapter(initial_oral_map={})
speaker = SpeakerResolverAdapter()
service = SmartMinutesService(retrieval, mapping, speaker)
```

### 3.3 接口与契约

| 接口 | 说明 |
|------|------|
| **POST /api/v1/smart-minutes/generate** | 生成纪要，请求体为 `MinutesRequest` 的 JSON，响应为 `MinutesResponse` |
| **POST /api/v1/smart-minutes/generate-stream** | 流式生成纪要，SSE 协议返回阶段事件与正文 token |
| **POST /api/v1/smart-minutes/retrieve** | 仅检索，不生成正文；请求体同，响应中 `minutes_content` 为空，`references` 等有值 |
| **POST /api/v1/smart-minutes/ingest-from-md** | MD 文件入库，将 Markdown 文件解析为 chunk 后存入 Milvus |
| **GET /health** | 健康检查 |

*注：原 `/api/smart-minutes/*` 路径继续保留作为兼容层，但推荐使用 `/api/v1/` 前缀。*

`/api/v1/schema/*` 为内部管理接口（Schema 注册/迁移/预览），不建议作为业务侧对外契约直接依赖。

请求/响应字段见 [使用指南 - 请求与响应](USAGE.md#二请求与响应)。

### 3.4 流式接口与 SSE 协议
 
接口：`POST /api/v1/smart-minutes/generate-stream`
 
响应为 `Content-Type: text/event-stream`，包含两类消息：
 
1. **阶段事件 (Stage Event)**：
   - 格式：`data: {"stage": "...", "think": "...", ...}`
   - 用途：前端展示"正在执行某步骤"。
   - 关键事件：
     - `smart_minutes_start`：开始执行。
     - `prepare_done`：工具执行完毕，上下文准备就绪（含 token 预算）。
     - `warnings`：执行结束前的告警汇总。
 
2. **Token 数据 (OpenAI Chunk)**：
   - 格式：`data: {"object": "chat.completion.chunk", "choices": [{"delta": {"content": "..."}}]}`
   - 用途：流式拼接纪要正文。
   - 结束标志：`data: [DONE]`

---

## 四、与现有 Milvus 混合检索的对接要点

若已有 `MilvusHybridClient.search(query_text, knowledge_base_name, top_k, topic_filter=..., file_list=...)`：

1. **filter 扩展**：`RetrievalAdapter` 会拼 `filter` 表达式（含 `source`、`topic`、`level1`、`author`、`type`、`project`、`department`、`organization`）。若现有 client 的 `search` 支持 `filter=expr` 参数，直接传入即可；否则需在 client 侧增加对 `filter` 的支持，或由适配器只传 `topic_filter`/`file_list`（则部分过滤在应用层做）。
2. **返回格式**：client 返回的 hit 建议为 `hit["entity"]` 存标量、`hit["distance"]` 存分数；适配器会转为 `page_content`、`source` 等统一 dict。
3. **output_fields**：若需「口水稿→相似议题名」，检索结果中需包含 `topic` 字段，请在 client 的 `output_fields` 中加入 `topic`。
4. **权重透传**：适配器会透传 `dense_weight`、`sparse_weight`、`type_weight`（以及其他 `*_weight` 参数）到底层 `search`。若底层不支持，请在 client 适配层忽略或实现加权逻辑。

### 4.1 分类型检索封装（todo/open_issue/conclusion）

`smart_minutes.tools.rag` 已提供分类型检索封装：

- `retrieve_similar_todos(...)`
- `retrieve_similar_open_issues(...)`
- `retrieve_similar_conclusions(...)`
- `retrieve_similar_todos_or_issues(...)`（双路检索融合排序）

可通过请求 `options.retrieval_weights` 配置权重，路由会自动透传到工具层。
若配置了 meeting_type 模板且请求中带 `meeting_type`，则请求未显式提供的参数会从模板补齐：

```json
{
  "options": {
    "retrieval_weights": {
      "todo": { "type_weight": 0.8, "dense_weight": 0.6, "sparse_weight": 0.4 },
      "open_issue": { "type_weight": 1.4, "dense_weight": 0.7, "sparse_weight": 0.3 },
      "conclusion": { "type_weight": 1.2, "dense_weight": 0.65, "sparse_weight": 0.35 }
    }
  }
}
```

---

## 五、数据约定（Milvus Schema）

为保证检索与过滤正确，入库时需约定：

- `source`：`minutes`（纪要）/ `attachment`（附件）/ `draft`（口水稿）
- `type`：`summary` / `open_issue` / `conclusion` / `todo` / `draft_segment` / `policy_chunk` 等
- `level1`：会议类型或会议名称（同系列过滤）
- `topic`：议题名
- `author`：发言人正式名
- `time`：ISO 时间戳（同系列最新排序）

对 `source=minutes` 建议启用分索引校验规则（已在 `pipelines/ingest.py` 支持）：

- `todo`：必须有 `owner`；
- `open_issue`：建议带 `next_step` / `issue_reason`；
- `conclusion`：建议为决策句；
- 支持别名归一化：`decision -> conclusion`、`action_item/task -> todo`、`issue -> open_issue`。

详见项目计划文档「五、数据模型与存储」。

---

## 六、MilvusClient 适配器

`smart_minutes/adapters/milvus_client.py` 提供了完整的 Milvus 客户端封装。

### 6.1 功能特性

- **连接池管理**：自动管理 Milvus 连接，支持并发访问
- **Schema 管理**：支持动态字段，自动创建集合和索引
- **数据操作**：插入、查询、删除、批量操作
- **向量搜索**：支持 ANN 搜索、混合搜索、标量过滤
- **迁移工具**：支持迁移到支持动态字段的新 Collection

### 6.2 使用示例

```python
from smart_minutes.adapters.milvus_client import (
    MilvusClient, MilvusConfig, CollectionSchemaConfig, IndexConfig
)

# 创建客户端
config = MilvusConfig(
    uri="http://localhost:19530",
    token="your-token",
    db_name="default"
)
client = MilvusClient(config)

# 创建集合（启用动态字段）
schema_config = CollectionSchemaConfig(
    collection_name="minutes",
    vector_dim=768,
    enable_dynamic_field=True,
    scalar_fields=[
        {"name": "source", "dtype": "VARCHAR", "max_length": 64},
        {"name": "type", "dtype": "VARCHAR", "max_length": 64},
        {"name": "topic", "dtype": "VARCHAR", "max_length": 256},
    ]
)
index_config = IndexConfig(index_type="IVF_FLAT", params={"nlist": 128})

client.create_collection(
    schema_config=schema_config,
    index_config=index_config,
    load_immediately=True
)

# 插入数据
rows = [
    {
        "text": "会议纪要内容",
        "vector": [0.1, 0.2, ...],  # 768维向量
        "source": "minutes",
        "type": "summary",
        "topic": "需求评审",
        # 动态字段
        "importance": 5,
        "keywords": ["需求", "评审"]
    }
]
client.insert("minutes", rows)

# 向量搜索
results = client.search(
    collection_name="minutes",
    vectors=[[query_vector]],
    search_params=SearchParams(top_k=5, filter_expr='type == "summary"')
)
```

### 6.3 动态字段支持

启用 `enable_dynamic_field=True` 后，可以在插入数据时添加任意额外字段：

```python
# 基础字段（Schema 中定义的）
row = {
    "text": "...",
    "vector": [...],
    "source": "minutes",
    "type": "conclusion"
}

# 动态扩展字段（自动生成）
row["importance"] = 5
row["sentiment"] = "positive"
row["custom_tag"] = "urgent"
```

### 6.4 检索适配器

`RetrievalAdapter` 包装 `MilvusClient`，实现 `IRetrieval` 接口：

```python
from smart_minutes.adapters.retrieval import create_retrieval_adapter

retrieval = create_retrieval_adapter(
    collection_name="minutes",
    milvus_uri="http://localhost:19530",
    token="your-token",
    db_name="default"
)

# 使用检索接口
results = retrieval.search(
    query_text="需求评审",
    topic_filter="需求评审",
    source_filter="minutes",
    top_k=5
)
```

---

## 七、MD 文件入库对接

系统支持将 Markdown 文件解析为 chunk 后入库 Milvus，便于历史文档的检索和引用。

### 7.1 使用场景

- 历史会议纪要文档入库
- 产品需求文档入库
- 政策文件入库
- 其他结构化文档入库

### 7.2 接口说明

**POST /api/v1/smart-minutes/ingest-from-md**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| kb_name | string | 是 | 知识库名（对应文件夹） |
| file_name | string | 是 | 文档名（对应子文件夹） |
| collection_name | string | 否 | 集合名，默认使用环境变量配置 |

### 7.3 文件路径结构

```
{FILE_PATH}/
  ├── {kb_name}/
  │   ├── {file_name}/
  │   │   └── vlm/
  │   │       └── *.md
  │   └── ...
  └── ...
```

**说明**：产品对外主要暴露 MD 入库接口；`pipelines/ingest.py` 中的 `ingest_minutes_chunks`、`ingest_attachments` 等直接 chunk/附件入库函数仅用于脚本与离线流水线，不作为业务 API 对外暴露。

### 7.4 入库流程

1. **读取文件**：从指定路径读取所有 `.md` 文件
2. **解析内容**：提取文本内容和元数据
3. **分块处理**：按段落/标题切分为 chunk
4. **向量化**：调用 Embedding 服务生成向量
5. **生成扩展字段**：使用 LLM 生成 summary、keywords 等
6. **删除旧数据**：根据 source_id 删除该文档的历史数据
7. **插入新数据**：将 chunk 和向量写入 Milvus

### 7.5 代码示例

```python
from smart_minutes import create_service

service = create_service()

# 入库 MD 文件
result = service.ingest_from_md(
    kb_name="product_docs",
    file_name="requirements",
    collection_name="minutes"
)

print(f"成功: {result['success']}")
print(f"入库数量: {result['ingested_count']}")
print(f"删除数量: {result['deleted_count']}")
if result['errors']:
    print(f"错误: {result['errors']}")
```

### 7.6 环境变量配置

```bash
# MD 文件存放路径
export FILE_PATH=./data/files

# Milvus 配置
export MILVUS_COLLECTION_NAME=minutes
export MILVUS_URI=http://localhost:19530
```

### 7.7 Pipeline 与 MD 入库对接方式

**推荐方式（选项 A）**：由 Pipeline 在 MD 文件就绪后**主动调用**入库接口，无需 callback 接收端。

1. Pipeline 将 MD 文件写入约定路径：`{FILE_PATH}/{kb_name}/{file_name}/vlm/*.md`
2. 写入完成后，Pipeline 调用 `POST /api/v1/smart-minutes/ingest-from-md`，请求体示例：
   ```json
   {"kb_name": "product_docs", "file_name": "requirements", "collection_name": "minutes"}
   ```
3. 服务端从本地路径读取 MD，解析后入库 Milvus

**可选方式（选项 B）**：若需 Webhook 接收端（如 MD 通过 URL 拉取），可新增 `POST /api/v1/smart-minutes/callback/ingest-ready`，请求体含 `kb_name`、`file_name`、可选 `file_url`；服务端校验后拉取或使用本地路径，再调用现有 `ingest_from_md`。采用 B 时需约定鉴权与幂等策略。

当前实现按**选项 A**：文档约定由 Pipeline 主动调用入库接口；`collection_name` 可与 `kb_name` 相同或由配置映射。

---

## 八、错误与降级

- 响应中 `partial=true` 表示部分成功（如某路检索失败、映射未命中）。
- 未完成项会写入 `warnings`；严重错误可写入 `errors`。
- 即使部分失败，仍会尽量返回已生成的 `minutes_content` 与 `references`，便于调用方降级展示或重试。

---

## 九、版本与兼容

- 对外契约以 `smart_minutes.schemas` 中的 `MinutesRequest`、`MinutesResponse` 为准；新增可选字段保持向后兼容。
- 内部 Agent、工具、路由可能随版本调整，调用方仅依赖门面与契约即可。

---

## 十、更新日志

| 日期 | 更新内容 |
|------|----------|
| 2026-02-28 | 初始版本 |
| 2026-03-02 | 补充 MD 文件入库对接章节（第7节） |
| 2026-03-02 | 补充 MilvusClient 动态字段支持说明 |
| 2026-03-03 | 补充 Pipeline/Callback 对接方式（7.7 节） |
