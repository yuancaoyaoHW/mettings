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
- 生成纪要：`POST http://localhost:8000/api/smart-minutes/generate`
- 仅检索：`POST http://localhost:8000/api/smart-minutes/retrieve`

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

---

## 二、请求与响应

### 2.1 请求体（MinutesRequest）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| meeting_type | string | 否 | 会议类型 |
| meeting_name | string | 否 | 会议名称 |
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
| mapped_terms | string[] | 本场用到的专业词（或口头→人名解析结果） |
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

调用 **POST /api/smart-minutes/retrieve** 时请求体同上；响应中 `minutes_content` 为空，`references`、`mapped_terms`、`resolved_speakers` 为检索与映射结果。

---

## 三、环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| MILVUS_URI | Milvus 连接地址 | |
| MILVUS_TOKEN | Milvus 认证 token | |
| MILVUS_DB_NAME | 数据库名 | |
| MILVUS_COLLECTION_NAME | 集合名 | |
| EMBEDDING_BASE_URL | Embedding 服务地址 | |
| EMBEDDING_MODEL_NAME | 模型名 | |
| LLM_API_KEY | LLM 密钥 | |
| LLM_BASE_URL | LLM 服务地址 | |
| LLM_MODEL_NAME | 模型名 | |
| CONTEXT_TOKEN_BUDGET | 单次上下文 token 上限 | 8000 |
| DEFAULT_TOP_K | 默认召回条数 | 5 |
| MAPPING_DB_URI | 映射表 DB（可选） | |

更多见项目根目录 `.env.example`。

---

## 四、能力与输入对应关系

| 你提供的输入 | 模块会做的事 |
|--------------|----------------|
| 会议类型/名称 | 查同系列最新历史纪要作模板、相关附件与专业词 |
| 议题名称 | 查同/似议题历史（总结、遗留）、在附件中搜关键信息、按议题切口水稿 |
| 人名/口头称呼 | 口头→正式名映射、查该人相关历史纪要 |
| 口水稿全文 + 议题 | 按议题分割口水稿；用口水稿查相似历史议题名 |
| 待办/结论片段 | 查类似历史待办、结论 |
| 人脸/声纹/会场 | 融合为当前发言人正式名 |

---

## 五、常见问题

**Q：返回的 minutes_content 是占位文案？**  
A：当前默认未接 LLM，仅为占位。对接真实 LLM 后会在门面内调用生成正文。

**Q：references 为空？**  
A：未注入真实 Milvus 客户端或集合无数据时，检索结果为空。请按《对接手册》注入 `RetrievalAdapter` 并配置正确集合。

**Q：如何只做「口头→人名」或「会议类型→专业词」？**  
A：调用 **POST /api/smart-minutes/retrieve**，请求中只填 `oral_names` 或 `meeting_type`/`meeting_name`，看响应中的 `mapped_terms`。

**Q：partial 为 true 时怎么处理？**  
A：表示部分步骤失败或未命中，可查看 `warnings` 列表；已生成的内容和 `references` 仍可使用，可按需降级展示或重试。
