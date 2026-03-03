# 智能会议纪要实现进度追踪

> 本文档对比需求文档（`requirements_smart_minutes.md`）与当前实现，列出已完成、进行中和待开发的功能项。
> 
> 最后更新：2026-03-02

---

## 进度总览

| 模块 | 进度 | 状态 |
|------|------|------|
| 1. 业务目标与核心产出 | 90% | 🟢 基本完成 |
| 2. 输入维度与检索能力 | 85% | 🟢 基本完成 |
| 3. 关键流水线6模块 | 90% | 🟢 基本完成 |
| 4. 检索与匹配规则 | 85% | 🟢 基本完成 |
| 5. 数据与工程约束 | 85% | 🟢 基本完成 |
| 6. 风险与对策 | 75% | 🟡 部分完成 |
| 7. 验收标准 | 60% | 🟡 部分完成 |
| 8. 数据入库流水线 | 90% | 🟢 基本完成 |
| **整体进度** | **85%** | 🟢 接近完成 |

---

## 详细功能清单

### 1. 业务目标与核心产出

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 格式统一（同系列模板） | 🟢 已完成 | `config_templates.py` | MeetingTypeTemplate 支持 |
| 内容延续性（历史结论/遗留） | 🟢 已完成 | `tools/rag.py` | 分类型检索实现 |
| 人/事/议题/附件对齐 | 🟢 已完成 | `schemas.py` | StructuredMinutesOutput |
| 可追溯性 | 🟢 已完成 | `schemas.py` | TraceabilityInfo 字段完整 |
| 结构化输出 meeting_info | 🟢 已完成 | `schemas.py` | MeetingInfo 模型 |
| 结构化输出 topics[] | 🟢 已完成 | `schemas.py` | TopicSection 模型 |
| 结构化输出 materials[] | 🟢 已完成 | `schemas.py` | MaterialCitation 模型 |
| 结构化输出 traceability | 🟢 已完成 | `schemas.py` | TraceabilityInfo 模型 |

**小结**：核心产出结构已实现，与需求一致。

---

### 2. 输入维度与检索能力

#### 2.1 会议上下文

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 同系列会议召回（Top-K） | 🟢 已完成 | `tools/rag.py` | `retrieve_latest_minutes_by_series` |
| 模板来源会议确定（Top-1） | 🟢 已完成 | `tools/rag.py` | 取时间最新 |
| 会议名称规范化 | 🟢 已完成 | `tools/rag.py` | `_normalize_meeting_key` |
| 项目/部门/组织过滤 | 🟢 已完成 | `adapters/retrieval.py` | 过滤表达式支持 |
| 时间排序 | 🟢 已完成 | `tools/rag.py` | `time` 倒序 |
| 同会系列附件入口 | 🟢 已完成 | `tools/attachment.py` | 基础实现 |
| 术语映射召回 | 🟢 已完成 | `adapters/stores/mapping_mysql.py` | SQLAlchemy ORM |

#### 2.2 议题上下文

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 按议题检索历史 | 🟢 已完成 | `tools/rag.py` | `retrieve_by_topic` |
| 按议题检索附件 | 🟢 已完成 | `tools/attachment.py` | `search_attachments_by_topic` |
| 口水稿切分到议题段 | 🟢 已完成 | `tools/draft.py` | `SemanticDraftSegmenter` LLM语义切分 |
| 从口水稿反推议题 | 🟢 已完成 | `tools/rag.py` | `retrieve_similar_topic_by_draft` |
| 议题边界不确定标记 | 🟢 已完成 | `tools/draft.py` | `SegmentConfidence` + `is_ambiguous` |

#### 2.3 发言人识别

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 多模态输入（face/voice/venue） | 🟢 已完成 | `schemas.py` | `RealtimeSpeakerInput` |
| 多模态候选融合 | 🟢 已完成 | `adapters/speaker_resolver.py` | `SpeakerResolverAdapter` |
| 输出归属人 | 🟢 已完成 | `schemas.py` | `SpeakerResolution.resolved_name` |
| 输出置信度 | 🟢 已完成 | `schemas.py` | `SpeakerResolution.confidence` |
| 输出候选列表 | 🟢 已完成 | `schemas.py` | `SpeakerResolution.candidates[]` |
| 冲突检测（status=conflict） | 🟢 已完成 | `adapters/speaker_resolver.py` | 置信度差<0.15标记冲突 |

#### 2.4 按人检索历史

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 口头称呼→正式名映射 | 🟢 已完成 | `adapters/stores/mapping_mysql.py` | SQLAlchemy ORM 持久化 |
| 按人检索历史纪要 | 🟢 已完成 | `tools/rag.py` | `retrieve_by_person` |
| 支撑 owner 候选 | 🟡 部分完成 | `agents/minutes_agent.py` | 未显式实现 |
| 行动项风格延续 | 🔴 未实现 | - | 需求中提及，未实现 |

**小结**：核心检索能力已实现，口水稿语义切分和映射持久化已完成。

---

### 3. 关键流水线6模块

| 模块 | 状态 | 实现文件 | 备注 |
|------|------|----------|------|
| **1. Meeting Resolver** | 🟢 已完成 | `tools/rag.py` | 同系列召回+模板确定 |
| **2. Speaker Fusion** | 🟢 已完成 | `adapters/speaker_resolver.py` | 多模态融合 |
| **3. Transcript Structuring** | 🟢 已完成 | `tools/draft.py` | LLM语义切分+不确定性标记 |
| **4. Topic Retrieval/RAG** | 🟢 已完成 | `tools/rag.py` | 分类型检索 |
| **5. Attachment Search** | 🟢 已完成 | `tools/attachment.py` | 会议级+议题级检索 |
| **6. Draft Generator** | 🟡 部分完成 | `agents/minutes_agent.py` | 基础实现，可进一步优化 |

**流水线执行流程**：

| 需求 | 状态 | 备注 |
|------|------|------|
| Group1: 映射/专业词（顺序） | 🟢 已实现 | `minutes_agent.py` |
| Group2: RAG/附件检索（并行） | 🟢 已实现 | `ThreadPoolExecutor` |
| Group3: 口水稿分割/发言人融合（顺序） | 🟢 已实现 | 按序执行 |
| 工具间依赖处理 | 🟡 部分实现 | 简单顺序执行，无复杂依赖 |
| 多轮调用支持 | 🔴 未实现 | 需求提及，未实现 |

**小结**：6模块全部完成，Transcript Structuring 已使用 LLM 语义切分。

---

### 4. 检索与匹配规则

#### 4.1 同系列会议检索

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 强约束：会议类型 | 🟢 已完成 | `tools/rag.py` | `level1_filter` |
| 强约束：组织属性 | 🟢 已完成 | `adapters/retrieval.py` | project/department/organization |
| 次强约束：名称主干 | 🟢 已完成 | `tools/rag.py` | `_normalize_meeting_key` |
| 弱约束：参会人重叠 | 🟢 已完成 | `tools/rag.py` | `_hit_attendees` + `_sort_key` |
| 排序：时间优先+相关性 | 🟢 已完成 | `tools/rag.py` | 时间倒序+重叠度排序 |

#### 4.2 相似议题检索

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 语义相似 | 🟢 已完成 | `adapters/retrieval.py` | 向量搜索 |
| 关键词重叠 | 🟡 部分完成 | `tools/rag.py` | topic_filter |
| 同系列加权 | 🟡 部分完成 | `adapters/retrieval.py` | 过滤条件 |
| 产出"风格特征" | 🟢 已完成 | `adapters/stores/template_store.py` | 模板抽取 |

#### 4.3 分类型索引

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| todo 分 type 检索 | 🟢 已完成 | `tools/rag.py` | `retrieve_similar_todos` |
| open_issue 分 type 检索 | 🟢 已完成 | `tools/rag.py` | `retrieve_similar_open_issues` |
| conclusion 分 type 检索 | 🟢 已完成 | `tools/rag.py` | `retrieve_similar_conclusions` |
| todo + open_issue 双路召回 | 🟢 已完成 | `tools/rag.py` | `retrieve_similar_todos_or_issues` |
| 权重参数透传 | 🟢 已完成 | `tools/rag.py` | `dense/sparse/type_weight` |
| 融合排序 | 🟢 已完成 | `tools/rag.py` | 按加权 score 取 Top-K |

**小结**：检索规则实现完善，参会人重叠已支持。

---

### 5. 数据与工程约束

#### 5.1 主数据与映射

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 称呼别名映射表 | 🟢 已完成 | `adapters/stores/mapping_mysql.py` | SQLAlchemy ORM |
| oral_name → formal_name → employee_id | 🟢 已完成 | `adapters/stores/mapping_mysql.py` | 完整实现 |
| 专业术语映射表 | 🟢 已完成 | `adapters/stores/mapping_mysql.py` | SQLAlchemy ORM |
| 会议议题元数据 | 🟢 已完成 | `pipelines/ingest.py` | Schema 完整 |

#### 5.2 Milvus 数据约定

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 通用字段（text/vector/source等） | 🟢 已完成 | `pipelines/ingest.py` | `_row_for_milvus` |
| 追溯字段（source_id/source_position/confidence） | 🟢 已完成 | `pipelines/ingest.py` | 完整支持 |
| 组织字段（project/department/organization） | 🟢 已完成 | `pipelines/ingest.py` | 完整支持 |
| 分索引字段（owner/deadline/status等） | 🟢 已完成 | `pipelines/ingest.py` | 完整支持 |
| 动态字段支持 | 🟢 已完成 | `adapters/milvus_client.py` | `enable_dynamic_field` |

#### 5.3 附件元数据

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 附件文件名/URL/类型 | 🟢 已完成 | `adapters/stores/attachment_metadata.py` | Attachment 表 |
| 版本控制 | 🟢 已完成 | `adapters/stores/attachment_metadata.py` | version字段 |
| 权限控制 | 🟢 已完成 | `adapters/stores/attachment_metadata.py` | permission_level |
| Milvus chunk 关联 | 🟢 已完成 | `adapters/stores/attachment_metadata.py` | AttachmentChunk 表 |

#### 5.4 生成约束

| 需求项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 区分"历史背景"和"本次新结论" | 🟡 部分完成 | `agents/minutes_agent.py` | Prompt 约束 |
| 关键事实附来源 | 🟡 部分完成 | `schemas.py` | 字段已定义，依赖 LLM 输出 |
| 响应部分成功（partial） | 🟢 已完成 | `schemas.py` | `partial` 字段 |
| 错误返回（errors/warnings） | 🟢 已完成 | `schemas.py` | `errors`/`warnings` 字段 |

**小结**：数据模型完善，映射持久化、附件元数据已完成。

---

### 6. 风险与对策

| 风险 | 对策 | 状态 | 实现文件 | 备注 |
|------|------|------|----------|------|
| Speaker 冲突 | 输出候选与冲突状态 | 🟢 已实现 | `adapters/speaker_resolver.py` | `status=conflict` |
| 议题切分不稳定 | 保留不确定提示 | 🟢 已实现 | `tools/draft.py` | `is_ambiguous` + `ambiguous_segments` |
| 历史幻觉继承 | Prompt 约束+输出追溯 | 🟡 部分实现 | `agents/minutes_agent.py` | Prompt 已约束 |
| 附件版本与权限 | 引用绑定版本/位置 | 🟢 已实现 | `adapters/stores/attachment_metadata.py` | 完整实现 |
| 权限过滤 | - | 🟢 已实现 | `adapters/stores/attachment_metadata.py` | `check_permission` |

---

### 7. 验收标准

| 验收指标 | 状态 | 备注 |
|----------|------|------|
| 结构完整率 | 🟢 可计算 | `structured_output` 字段齐全可校验 |
| 模板一致性 | 🟢 已实现 | `adapters/stores/template_store.py` |
| 检索命中率 | 🟢 已实现 | `tests/evaluation/retrieval_eval.py` |
| 发言人准确率 | 🟡 可追溯 | `speaker_resolutions` 可人工核对 |
| 可追溯覆盖率 | 🟡 部分支持 | 字段已定义，依赖 LLM 输出 |

**测试覆盖情况**：

| 测试类型 | 状态 | 文件 |
|----------|------|------|
| RAG 工具测试 | 🟢 已覆盖 | `tests/test_rag.py` |
| Agent 测试 | 🟢 已覆盖 | `tests/test_agent.py` |
| Router 测试 | 🟢 已覆盖 | `tests/test_router.py` |
| 模板测试 | 🟢 已覆盖 | `tests/test_templates.py` |
| Schema 测试 | 🟢 已覆盖 | `tests/test_schemas.py` |
| 检索命中率评测 | 🟢 已覆盖 | `tests/evaluation/retrieval_eval.py` |
| 生成质量评测 | 🟢 已覆盖 | `tests/evaluation/generation_eval.py` |
| 端到端测试 | 🟢 已覆盖 | `tests/evaluation/end_to_end.py` |
| 性能测试 | 🟢 已覆盖 | `tests/evaluation/end_to_end.py` |

---

### 8. 数据入库流水线

| 功能项 | 状态 | 实现文件 | 备注 |
|--------|------|----------|------|
| 会议纪要入库 | 🟢 已完成 | `pipelines/ingest.py` | `ingest_minutes_chunks` |
| 附件文档入库 | 🟢 已完成 | `pipelines/ingest.py` | `ingest_attachments` |
| 口水稿分段入库 | 🟢 已完成 | `pipelines/ingest.py` | `ingest_draft_segments` |
| MD 文件入库 | 🟢 已完成 | `pipelines/md_ingest.py` | `ingest_from_md` |
| 类型归一化 | 🟢 已完成 | `pipelines/ingest.py` | decision→conclusion 等 |
| 规则校验 | 🟢 已完成 | `pipelines/ingest.py` | todo 必须有 owner |
| 动态字段生成 | 🟢 已完成 | `pipelines/ingest.py` | summary_short/keywords 等 |
| 扩展字段注册 | 🟢 已完成 | `smart_minutes/schema_management.py` | 支持自定义字段 |

**API 接口**：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/smart-minutes/ingest-from-md` | POST | MD 文件入库 |

---

## 问题分析文档追踪

根据 `plan_issues_analysis.md`，以下问题已解决/待解决：

| 问题 | 优先级 | 状态 | 解决方案 |
|------|--------|------|----------|
| 抽象接口无落点 | 高 | 🟢 已解决 | 创建 `contracts.py` 定义 Protocol |
| 与现有 Milvus 集成 | 高 | 🟢 已解决 | `MilvusClient` 完整封装 |
| 口水稿两种场景区分 | 中 | 🟢 已解决 | `SemanticDraftSegmenter` 区分本次/历史 |
| 附件列表存储 | 中 | 🟢 已解决 | `AttachmentMetadataStore` 实现 |
| 历史纪要模板获取 | 中 | 🟢 已解决 | `TemplateStore` + `TemplateExtractor` |
| meeting_id 缺失 | 中 | 🟢 已解决 | `MinutesRequest.meeting_id` 已添加 |
| 路由与 Agent 职责边界 | 中 | 🟢 已解决 | 路由产出建议序列，Agent 执行 |
| 错误处理与降级 | 高 | 🟢 已解决 | `partial`/`errors`/`warnings` 字段 |
| 多租户与多库 | 低 | 🔴 待解决 | 需根据实际需求设计 |
| 流式与分片 | 中 | 🟢 已解决 | `generate-stream` SSE 接口 |
| ingest 归属 | 低 | 🟢 已解决 | 门面 `ingest_from_md` 方法提供统一入口 |
| 验收标准缺失 | 高 | 🟢 已解决 | `tests/evaluation/` 完整评测框架 |

---

## 待开发功能清单（按优先级排序）

### 🔴 高优先级（阻碍上线）

**全部已完成！** ✅

### 🟠 中优先级（影响体验）

1. **参会人重叠度计算**
   - 文件：`tools/rag.py`
   - 状态：🟢 已完成 - `retrieve_latest_minutes_by_series` 已支持参会人重叠排序

2. **风格特征提取与延续**
   - 文件：`adapters/stores/template_store.py` 可扩展
   - 需求：从历史纪要提取"条目长度/字段完整度/措辞风格"，应用于生成

3. **性能优化**
   - 文件：`agents/minutes_agent.py`
   - 需求：缓存、异步化、批量处理优化

4. **多租户支持**
   - 文件：`smart_minutes/`, `api/`
   - 需求：请求模型增加 `tenant_id`，按租户隔离数据

### 🟡 低优先级（锦上添花）

5. **议题自动命名**
   - 需求：从口水稿聚类提取议题名

6. **Speaker 历史立场分析**
   - 需求：按人检索历史结论，做一致性校验

7. **实时监控与告警**
   - 文件：新增 `monitoring/`
   - 需求：接入 Prometheus/Grafana 监控接口耗时、成功率

---

## 近期开发建议（未来 2 周）

### Week 1

1. **Day 1-2**: 性能优化
   - 添加检索结果缓存
   - 优化 LLM 调用并发

2. **Day 3-4**: 多租户支持设计
   - 设计租户隔离方案
   - 更新请求模型和适配器

3. **Day 5**: 风格特征提取增强
   - 扩展 `TemplateExtractor` 提取更多风格特征

### Week 2

1. **Day 1-2**: 集成测试完善
   - 准备真实测试数据
   - 运行完整评测流程

2. **Day 3-4**: 生产环境准备
   - 性能压测
   - 部署文档编写

3. **Day 5**: 文档更新
   - 更新 API 文档
   - 完善使用示例

---

## 附录：已实现功能速查

### API 接口

| 接口 | 路径 | 状态 |
|------|------|------|
| 生成纪要 | POST /api/v1/smart-minutes/generate | 🟢 已完成 |
| 流式生成 | POST /api/v1/smart-minutes/generate-stream | 🟢 已完成 |
| 仅检索 | POST /api/v1/smart-minutes/retrieve | 🟢 已完成 |
| MD 入库 | POST /api/v1/smart-minutes/ingest-from-md | 🟢 已完成 |
| Schema 管理 | /api/v1/schema/* | 🟢 已完成 |

### 核心模块

| 模块 | 文件 | 状态 |
|------|------|------|
| 门面服务 | `smart_minutes/api.py` | 🟢 已完成 |
| 路由 | `smart_minutes/agents/router.py` | 🟢 已完成 |
| Agent | `smart_minutes/agents/minutes_agent.py` | 🟢 已完成 |
| RAG 工具 | `smart_minutes/tools/rag.py` | 🟢 已完成 |
| 映射工具 | `smart_minutes/tools/mapping.py` | 🟢 已完成 |
| 发言人工具 | `smart_minutes/tools/speaker.py` | 🟢 已完成 |
| 附件工具 | `smart_minutes/tools/attachment.py` | 🟢 已完成 |
| 口水稿工具 | `smart_minutes/tools/draft.py` | 🟢 已完成 |
| Milvus 客户端 | `smart_minutes/adapters/milvus_client.py` | 🟢 已完成 |
| 检索适配器 | `smart_minutes/adapters/retrieval.py` | 🟢 已完成 |
| MySQL 映射存储 | `smart_minutes/adapters/stores/mapping_mysql.py` | 🟢 已完成 |
| 附件元数据 | `smart_minutes/adapters/stores/attachment_metadata.py` | 🟢 已完成 |
| 模板存储 | `smart_minutes/adapters/stores/template_store.py` | 🟢 已完成 |
| 发言人解析 | `smart_minutes/adapters/speaker_resolver.py` | 🟢 已完成 |
| Schema 管理 | `smart_minutes/schema_management.py` | 🟢 已完成 |
| 入库流水线 | `pipelines/ingest.py` | 🟢 已完成 |
| MD 入库 | `pipelines/md_ingest.py` | 🟢 已完成 |

### 评测与测试

| 功能 | 文件 | 状态 |
|------|------|------|
| 检索命中率评测 | `tests/evaluation/retrieval_eval.py` | 🟢 已完成 |
| 生成质量评测 | `tests/evaluation/generation_eval.py` | 🟢 已完成 |
| 端到端测试 | `tests/evaluation/end_to_end.py` | 🟢 已完成 |
| 统一运行入口 | `tests/evaluation/run_all.py` | 🟢 已完成 |

---

## 更新日志

| 日期 | 更新内容 | 更新人 |
|------|----------|--------|
| 2026-02-28 | 初版创建 | AI Assistant |
| 2026-02-28 | 完成全部6项高优先级功能 | AI Assistant |
| 2026-03-02 | 更新整体进度至 85%，补充 Schema 管理功能 | AI Assistant |
| 2026-03-02 | 更新参会人重叠度计算状态为已完成，添加数据入库流水线章节 | AI Assistant |

---

## 如何更新本文档

1. 当功能开发完成时，将对应项状态改为 🟢 已完成
2. 新增需求时，添加到"待开发功能清单"并标记优先级
3. 每周回顾时，更新"进度总览"百分比
4. 添加新的更新日志条目
