# 智能纪要计划 — 问题分析

## 一、接口与抽象未落地

| 问题 | 说明 |
| --- | --- |
| **抽象接口无落点** | 计划要求依赖「检索接口」「映射查询接口」「发言人融合接口」等抽象，但目录中只有 `adapters/` 下的具体实现，没有约定接口定义所在位置（如 `contracts.py` 或 `interfaces.py`）。调用方注入时缺少明确的 Protocol/ABC 定义。 |
| **建议** | 在 `smart_minutes/` 下增加 `contracts.py`（或 `interfaces/`），显式定义 `IRetrieval`、`IMappingStore`、`ISpeakerResolver` 等，adapters 实现这些接口；门面构造函数接收接口类型而非具体类。 |

---

## 二、与现有代码的集成不清晰

| 问题 | 说明 |
| --- | --- |
| **MilvusHybridClient 归属** | 现有实现依赖 `src.model.kb_entity`、`src.util.llm_config_center`、`src.service.multi_files_compare` 等。若 smart_minutes 直接复用，会依赖 `src.*`，削弱「独立包、易组合」；若拷贝进包内，则双份维护、与现有混合检索分支易偏离。 |
| **Collection 名来源** | 现有接口用参数 `knowledge_base_name` 传 collection；计划写「由配置提供」。未说明：是模块初始化时从配置读一个默认 collection，还是每个请求可在 options 里覆盖；多租户时是否按 tenant_id 选 collection。 |
| **建议** | 明确采用「适配器包装现有 MilvusHybridClient」：smart_minutes 只依赖「检索接口」，适配器在项目根或共享层实现，内部调现有 client；collection 名由适配器从配置或请求上下文（如 tenant_id）解析，不写死在包内。 |

---

## 三、口水稿与附件的输入/存储矛盾

| 问题 | 说明 |
| --- | --- |
| **口水稿两种场景未区分** | 「按议题分割口水稿」可能指：(1) **本次会议**：请求体里的 `draft_text` + 本次议题列表，在内存中分割，不依赖 Milvus；(2) **历史会议**：已入库的口水稿，用 meeting_id + topic 在 Milvus 过滤。计划里工具写 `get_draft_segments_by_topics(meeting_id, topic_names)`，未区分「本次实时分割」与「历史按 topic 检索」，且本次会议可能尚无 meeting_id。 |
| **附件列表的存储** | 「get_attachments_by_meeting → 政策等列表」：Milvus 只存 chunk 的 source/level1/topic，没有「附件文件名、URL、类型」等元数据。要返回附件列表，要么在 Milvus 上做聚合（如按某 file_id 去重），要么另有附件元数据表/存储。计划未说明附件元数据存哪里、与 Milvus chunk 如何关联。 |
| **建议** | 口水稿：请求模型保留 `draft_text` 与 `topics`，门面内「本次分割」用内存逻辑（或调用 draft 工具时传入 draft_text+topics，无 meeting_id）；历史口水稿检索单独用 RAG filter source=draft。附件：明确是否有「附件元数据表」或约定用 Milvus 某字段（如 source 存 file_id）聚合出列表；若没有则补充数据模型。 |

---

## 四、模板抽取与 meeting_id 缺失

| 问题 | 说明 |
| --- | --- |
| **历史纪要模板如何得到** | 「从同系列最新 1～3 条纪要中提取结构（章节、字段名、表述习惯）」未定义实现方式：规则解析、LLM 一次性总结、还是预存 template 字段？若每次请求用 LLM 从最新纪要抽模板，延迟与成本高；若预存，当前 Schema 无 template 字段，需约定 level1/level2 或单独表如何表达模板。 |
| **meeting_id 未在请求中** | 工具签名中有 `meeting_id`（如 `get_draft_segments_by_topics(meeting_id, ...)`、`search_attachments_by_topic(meeting_id, ...)`），但 3.2 请求模型只有 meeting_type/meeting_name，没有 meeting_id。正在生成纪要的会议可能尚未持久化，没有 id。 |
| **建议** | 模板：在计划中二选一或组合——(a) 预存模板（在 ingest 时由 LLM 或规则生成并写入某存储/字段），或 (b) 每次用 LLM 从最新 N 条摘要抽模板并写明成本；若用 (a) 需补充 Schema 或元数据表。meeting_id：请求模型增加可选 `meeting_id`；若缺失则用 meeting_type + meeting_name 作为逻辑标识，在适配器内映射为 Milvus 的 level1 或外部附件/口水稿的查询键。 |

---

## 五、路由与 Agent 的职责边界

| 问题 | 说明 |
| --- | --- |
| **谁决定工具与顺序** | 路由输出「ordered list of tool calls」，MinutesAgent 再执行。若路由完全决定列表且 Agent 只按序执行，则 Agent 退化为执行器；若 Agent 可自主追加或跳过工具，则路由的 list 只是建议，需约定是否允许多轮、是否可覆盖。 |
| **多轮与依赖** | 例如「先查相似历史议题名，再按这些议题查附件」存在工具间依赖，计划未明确是否支持多轮调用、每轮输入是否依赖上一轮输出。 |
| **建议** | 在 6.1/6.3 中明确：路由产出「建议的工具序列 + 必要参数」，Agent 按序执行并可据结果决定是否追加调用（如检索为空则跳过依赖该结果的步骤）；或约定「单轮固定顺序、无多轮」，避免实现时理解分歧。 |

---

## 六、错误处理与降级

| 问题 | 说明 |
| --- | --- |
| **失败时的契约** | 检索为空、映射查不到、LLM 超时、发言人融合失败时，门面应返回什么？是否允许「部分成功」（如仅有历史模板、无附件）？响应模型是否包含 error_code、partial_results、warnings？ |
| **建议** | 在 3.2 响应模型中增加可选字段：如 `errors: List[ErrorItem]`、`warnings: List[str]`、`partial: bool`；在九、风险与依赖中增加「错误与降级」：约定超时与部分失败时的返回策略（如仍返回已生成的纪要 + references，未完成项写入 warnings）。 |

---

## 七、多租户与多库

| 问题 | 说明 |
| --- | --- |
| **租户隔离未细化** | 计划提到「不同租户的库」「collection 名由配置提供」，但请求模型只写 options 里可带 collection 名。未说明：是否每个请求带 tenant_id、门面或适配器是否按 tenant_id 选 collection/映射表/DB。 |
| **建议** | 若有多租户需求：在请求模型中增加可选 `tenant_id`（或 scope_id），并在「组合方式」中说明由门面/适配器根据 tenant_id 选择数据源；映射表是否按租户隔离也需一句约定。若无多租户，可明确写「当前不考虑多租户」，避免实现时猜。 |

---

## 八、长纪要、流式与性能

| 问题 | 说明 |
| --- | --- |
| **流式与分片** | 生成纪要可能很长，计划未提是否支持流式（SSE/WebSocket）或分片返回；若仅 `minutes_content: str` 一次性返回，长文可能超时或占内存。 |
| **时延** | 仅提到「多工具串行可能较慢、可并行」，未写具体策略（如哪些工具可并行、门面是否提供 async 接口）。 |
| **建议** | 若首版不做流式，在 3.2 或风险中写明「当前为一次性返回；长纪要场景后续可增加流式接口」。并行：在 6.3 中列出可并行的工具组合（如映射 + 多路 RAG 并行），便于实现时落实。 |

---

## 九、实施与验收

| 问题 | 说明 |
| --- | --- |
| **ingest 归属** | `pipelines/ingest` 在项目根下、不在 smart_minutes 包内。未明确：入库与向量化是「智能纪要功能的一部分」还是独立的数据准备流水线；若属于功能一部分，是否迁入 `smart_minutes/pipelines` 以便独立部署与版本一致。 |
| **验收标准缺失** | 各 Phase 缺少可验收标准（如 Phase 2：「同系列检索 top_k 准确率」「生成纪要与人工样本的相似度/满意度」），不利于排期与验收。 |
| **建议** | ingest：在四、目录建议中写明 ingest 是共享流水线还是 smart_minutes 子模块，以及由谁负责维护。Phase 1～5 各补充 1～2 条验收标准（可后补具体指标）。 |

---

## 十、实现细节不一致

| 问题 | 说明 |
| --- | --- |
| **Milvus hit 结构** | 6.2.1 写「需统一从 hit["entity"] 或 hit 取字段」——现有代码中既有 `hit["entity"].get("text")` 也有 `hit.get("text")`，本身不统一。计划未指定以哪种为准，实现易踩坑。 |
| **建议** | 在 6.2.1 或七、关键实现细节中明确：以 pymilvus hybrid_search 实际返回结构为准，例如「统一使用 hit["entity"] 取标量字段，distance 取 hit["distance"]」，并注明 Milvus 版本，避免歧义。 |

---

## 小结

- **必须补上的**：抽象接口落点、与现有 Milvus 的集成方式（适配器 + collection/租户）、请求中 meeting_id/tenant_id 与附件/口水稿数据来源的约定、错误与降级在响应模型中的体现。
- **建议补上的**：口水稿「本次分割」与「历史检索」的区分、附件元数据存储、模板抽取方式与 meeting_id 的替代方案、路由与 Agent 的职责与多轮约定、Phase 验收标准、ingest 归属、Milvus 返回结构统一约定。
- **可选补上的**：流式/分片、多租户详细设计、可并行工具列表。

按上述项在计划中做小幅增补，可减少实现阶段的反复与歧义。
