# 智能会议纪要系统 - 详细架构图

## 1. 整体数据流架构图

```mermaid
flowchart TB
    subgraph Input["输入层"]
        I1[会议类型/名称<br/>meeting_type/name]
        I2[议题列表<br/>topics]
        I3[口水稿<br/>draft_text]
        I4[多模态输入<br/>人脸/声纹/会场]
        I5[口头称呼<br/>oral_names]
        I6[待办/结论<br/>open_issues/conclusions]
        I7[扩展字段配置<br/>options.dynamic_fields]
    end

    subgraph Router["路由层 (agents/router.py)"]
        R1[参数合并<br/>请求 > 模板 > 默认]
        R2[工具序列生成<br/>suggest_tools]
        R3[权重计算<br/>retrieval_weights]
    end

    subgraph Tools["工具执行层 (tools/)"]
        direction TB
        T1["映射工具 (mapping)<br/>oral→formal / 专业词"] 
        T2["RAG检索 (rag)<br/>同系列/议题/人/类型"]
        T3["附件检索 (attachment)<br/>按会议/议题"]
        T4["口水稿切分 (draft)<br/>语义段落/议题对齐"]
        T5["发言人融合 (speaker)<br/>多模态融合"]
        T6["Chunk匹配 (chunk_topic_matcher)<br/>主题分配"]
        T7["专有名词 (proper_noun)<br/>LLM提取/存储"]
    end

    subgraph Agent["Agent编排 (agents/minutes_agent.py)"]
        A1[分组执行<br/>Group1顺序→Group2并行→Group3顺序]
        A2[结果汇总<br/>refs + speakers + terms]
        A3[上下文组装<br/>模板+历史+片段+术语]
        A4[预算裁剪<br/>context_token_budget]
        A5[LLM生成<br/>结构化输出/流式]
        A6[结果解析<br/>JSON提取+Topic合并]
    end

    subgraph SchemaMgmt["Schema管理 (schema_management.py)"]
        S1[扩展字段注册<br/>ExtensionFieldConfig]
        S2[字段生成<br/>LLM/Rule方式]
        S3[Schema迁移<br/>动态字段支持]
        S4[字段预览<br/>Preview Generation]
    end

    subgraph Output["输出层"]
        O1[纪要正文<br/>minutes_content]
        O2[结构化数据<br/>structured_output]
        O3[追溯信息<br/>references + traceability]
        O4[诊断信息<br/>warnings + errors + partial]
        O5[扩展字段值<br/>extension_fields]
    end

    Input --> Router
    Router --> Tools
    Tools --> Agent
    Agent --> Output
    SchemaMgmt -.->|动态字段| Tools
    SchemaMgmt -.->|字段生成| Output
```

---

## 2. 模块依赖关系图

```mermaid
flowchart LR
    subgraph External["外部依赖"]
        Milvus[(Milvus<br/>向量存储)]
        LLM[(LLM API<br/>Qwen3-30B-A3B)]
        Embed[(Embedding API<br/>4096维)]
        MySQL[(MySQL<br/>映射表/专有名词)]
        FaceAPI[(人脸/声纹API)]
    end

    subgraph Contracts["契约层 (contracts.py)"]
        I1[IRetrieval]
        I2[IMappingStore]
        I3[ISpeakerResolver]
    end

    subgraph Adapters["适配器层 (adapters/)"]
        A1[RetrievalAdapter]
        A2[MappingStoreAdapter<br/>内存/Mysql实现]
        A3[SpeakerResolverAdapter]
        A4[MilvusClient<br/>连接池/CRUD/搜索]
        A5[ProperNounStore<br/>SQLAlchemy ORM]
    end

    subgraph Core["核心层"]
        direction TB
        Schemas[(schemas.py<br/>Pydantic模型)]
        Config[(config.py<br/>配置管理)]
        Templates[(config_templates.py<br/>模板策略)]
        SchemaMgmt[(schema_management.py<br/>Schema扩展)]
        
        subgraph Agents["Agent层 (agents/)"]
            Router[router.py<br/>工具路由]
            MinutesAgent[minutes_agent.py<br/>执行编排]
        end
        
        subgraph Tools["工具层 (tools/)"]
            Rag[rag.py<br/>检索封装]
            Attach[attachment.py<br/>附件]
            Speaker[speaker.py<br/>发言人]
            Map[mapping.py<br/>映射]
            Draft[draft.py<br/>口水稿语义切分]
            ChunkMatch[chunk_topic_matcher.py<br/>Chunk匹配]
            ProperNoun[proper_noun_extractor.py<br/>专有名词提取]
        end
    end

    subgraph API["接口层 (api/)"]
        Service[SmartMinutesService<br/>统一门面]
        HTTP[main.py<br/>FastAPI HTTP服务]
        QueryRoutes[query_routes.py<br/>9大查询API]
        SchemaRoutes[schema_manager.py<br/>Schema管理API]
    end

    subgraph Pipeline["数据流水线 (pipelines/)"]
        Ingest[ingest.py<br/>入库与校验]
        MdIngest[md_ingest.py<br/>MD文件解析入库]
    end

    subgraph Services["服务层 (services/)"]
        LLMService[llm.py<br/>统一LLM调用]
        EmbedService[embedding.py<br/>统一Embedding]
    end

    %% 依赖关系
    Adapters --> Contracts
    A1 --> Milvus
    A1 --> A4
    A2 --> MySQL
    A3 --> FaceAPI
    A5 --> MySQL
    
    Tools --> Contracts
    Rag --> I1
    Attach --> I1
    Speaker --> I3
    Map --> I2
    ChunkMatch --> LLMService
    ProperNoun --> LLMService
    
    Agents --> Tools
    Agents --> Schemas
    Agents --> Config
    
    Service --> Agents
    Service --> Contracts
    Service --> SchemaMgmt
    HTTP --> Service
    QueryRoutes --> Service
    SchemaRoutes --> Service
    
    Pipeline --> EmbedService
    Pipeline --> LLMService
    Pipeline --> Milvus
    
    Services --> External
    SchemaMgmt --> A4
    
    Contracts -.-> Adapters
```

---

## 3. 详细请求处理流程图

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as FastAPI
    participant Service as SmartMinutesService
    participant Router as Router
    participant Agent as MinutesAgent
    participant Tools as 工具集
    participant LLM as LLM服务

    Client->>API: POST /generate<br/>MinutesRequest
    API->>Service: run(request)
    
    Service->>Router: suggest_tools(request)
    
    Note over Router: 参数合并优先级：<br/>请求options > meeting_type模板 > 全局默认<br/>支持retrieval_weights分类型权重
    
    Router->>Router: 解析retrieval_weights<br/>todo/open_issue/conclusion权重
    Router->>Router: 生成工具调用序列<br/>mapping→rag→attachment→draft→speaker
    Router-->>Service: tool_suggestions
    
    Service->>Agent: run(request, tool_suggestions)
    
    Note over Agent: Group1: 映射工具（顺序）
    Agent->>Tools: mapping (oral→formal)
    Tools-->>Agent: mapped_terms
    Agent->>Tools: professional_terms
    Tools-->>Agent: terms
    
    Note over Agent: Group2: 检索工具（并行）
    par 并行执行
        Agent->>Tools: retrieve_latest_minutes_by_series
        Tools-->>Agent: series_refs
    and
        Agent->>Tools: retrieve_by_topic
        Tools-->>Agent: topic_refs
    and
        Agent->>Tools: retrieve_by_person
        Tools-->>Agent: person_refs
    and
        Agent->>Tools: retrieve_similar_todos_or_issues
        Tools-->>Agent: todo_issue_refs
    and
        Agent->>Tools: retrieve_similar_conclusions
        Tools-->>Agent: conclusion_refs
    and
        Agent->>Tools: search_attachments_by_topic
        Tools-->>Agent: attachment_refs
    end
    
    Note over Agent: Group3: 后处理工具（顺序）
    Agent->>Tools: get_draft_segments_by_topics<br/>语义切分+置信度标记
    Tools-->>Agent: segments
    
    opt 有实时发言人输入
        Agent->>Tools: resolve_speaker<br/>(face/voice/venue融合)
        Tools-->>Agent: SpeakerResolution
    end
    
    Agent->>Agent: 结果汇总与去重
    Agent->>Agent: 组装上下文context<br/>历史模板>同类议题>专业词>发言人>口水稿
    Agent->>Agent: _truncate_to_budget<br/>(按token预算裁剪)
    
    Agent->>Agent: _build_prompts<br/>构建system/user prompt
    
    Agent->>LLM: 调用生成
    LLM-->>Agent: minutes_content
    
    Agent->>Agent: _parse_structured_topics<br/>从JSON块解析topics
    Agent->>Agent: _build_structured_output<br/>构造结构化结果
    
    Agent-->>Service: MinutesResponse
    Service-->>API: MinutesResponse
    API-->>Client: JSON响应<br/>含minutes_content+structured_output
```

---

## 4. 数据模型关系图

```mermaid
erDiagram
    MinutesRequest ||--o{ Topic : contains
    MinutesRequest ||--o{ RealtimeSpeaker : has
    MinutesRequest ||--o{ Options : has
    
    MinutesResponse ||--|| StructuredMinutesOutput : contains
    MinutesResponse ||--o{ ReferenceItem : references
    MinutesResponse ||--o{ SpeakerResolution : speakers
    MinutesResponse ||--o{ ErrorItem : errors
    
    StructuredMinutesOutput ||--|| MeetingInfo : meeting_info
    StructuredMinutesOutput ||--o{ TopicSection : topics
    StructuredMinutesOutput ||--o{ MaterialCitation : materials
    StructuredMinutesOutput ||--|| TraceabilityInfo : traceability
    
    TopicSection ||--o{ ActionItem : action_items
    SpeakerResolution ||--o{ SpeakerCandidate : candidates
    
    ExtensionFieldConfig ||--o{ SchemaMigrationRequest : migrates
    
    MinutesRequest {
        string meeting_type
        string meeting_name
        string meeting_time
        string project
        string department
        string organization
        string draft_text
        string topics
        string person_names
        string oral_names
        string open_issues
        string conclusions
        string options
        string realtime_speaker
    }
    
    TopicSection {
        string topic_name
        string summary
        string key_points
        string conclusions
        string open_issues
        string action_items
        string source_ref_ids
        number confidence
    }
    
    ActionItem {
        string content
        string owner
        string deadline
        string status
        string source_ref_ids
        string source_minutes_id
    }
    
    ReferenceItem {
        number pk
        number score
        string page_content
        string source
        string type
        string topic
        string author
        string time
        string source_id
        string source_position
        number confidence
        string owner
        string deadline
    }
    
    SpeakerResolution {
        string resolved_name
        number confidence
        string candidates
        string status
        string conflict_reason
    }
    
    TraceabilityInfo {
        string history_minutes_ids
        string attachment_positions
        string speaker_resolution
        string per_fact_sources
    }
    
    ExtensionFieldConfig {
        string field_name
        string field_type
        string description
        string generation_method
        string generation_prompt
        string rule_expression
        string enabled
    }
```

---

## 5. RAG检索策略细节图

```mermaid
flowchart TD
    subgraph Input["检索输入"]
        Q1[会议类型/名称]
        Q2[议题名称]
        Q3[人名]
        Q4[待办/遗留文本]
        Q5[结论文本]
        Q6[口水稿]
    end

    subgraph Filters["过滤条件"]
        F1[source: minutes/attachment/draft]
        F2[type: summary/todo/open_issue/conclusion]
        F3[level1: 会议类型/名称]
        F4[topic: 议题名]
        F5[author: 发言人]
        F6[project/department/organization]
        F7[dynamic_fields: 动态字段过滤]
    end

    subgraph Weights["权重配置"]
        W1[type_weight<br/>类型权重]
        W2[dense_weight<br/>向量权重]
        W3[sparse_weight<br/>关键词权重]
    end

    subgraph Strategy["检索策略"]
        S1["同系列会议<br/>retrieve_latest_minutes_by_series<br/>+ 参会人重叠排序"]
        S2["按议题检索<br/>retrieve_by_topic"]
        S3["按人检索<br/>retrieve_by_person"]
        S4["待办/遗留双路<br/>retrieve_similar_todos_or_issues<br/>加权融合"]
        S5["结论检索<br/>retrieve_similar_conclusions"]
        S6["口水稿语义<br/>retrieve_similar_topic_by_draft"]
        S7["附件检索<br/>search_attachments_by_topic"]
    end

    subgraph Merge["结果融合"]
        M1[加权重排序]
        M2[去重]
        M3[Top-K截取]
    end

    Q1 --> S1
    Q2 --> S2
    Q3 --> S3
    Q4 --> S4
    Q5 --> S5
    Q6 --> S6
    Q2 --> S7
    
    F1 --> S1
    F2 --> S4
    F3 --> S1
    F4 --> S2
    F5 --> S3
    F6 --> S1
    F7 --> S1
    
    W1 --> S4
    W2 --> S4
    W3 --> S4
    
    S1 --> M1
    S2 --> M1
    S3 --> M1
    S4 --> M1
    S5 --> M1
    S6 --> M1
    S7 --> M1
    
    M1 --> M2
    M2 --> M3
    M3 --> References[references列表<br/>带score/confidence/source]
```

---

## 6. 发言人融合决策流程图

```mermaid
flowchart TD
    Start([开始]) --> Input[输入: face_result<br/>voice_result<br/>venue_name]
    
    Input --> Collect[收集候选]
    
    Collect --> Venue{venue_name?}
    Venue -->|有| AddVenue[添加候选<br/>confidence=0.6<br/>source=venue]
    Venue -->|无| Face{face_result?}
    
    AddVenue --> Face
    
    Face -->|有| AddFace[添加候选<br/>confidence=face.conf<br/>source=face]
    Face -->|无| Voice{voice_result?}
    
    AddFace --> Voice
    
    Voice -->|有| AddVoice[添加候选<br/>confidence=voice.conf<br/>source=voice]
    Voice -->|无| CheckEmpty{候选为空?}
    
    AddVoice --> CheckEmpty
    
    CheckEmpty -->|是| Unknown[返回 unknown<br/>confidence=0<br/>conflict_reason=no_modal_signal]
    CheckEmpty -->|否| Sort[按confidence排序]
    
    Sort --> GetTop[取top候选]
    
    GetTop --> CheckTop2{存在top2且<br/>name不同且<br/>conf差<0.15?}
    
    CheckTop2 -->|是| Conflict[status=conflict<br/>conflict_reason=face_voice_close_confidence]
    CheckTop2 -->|否| CheckLowConf{top.confidence<0.5?}
    
    Conflict --> Output
    CheckLowConf -->|是| Unknown
    CheckLowConf -->|否| Resolved[status=resolved]
    
    Resolved --> Output[返回 SpeakerResolution<br/>resolved_name/confidence<br/>candidates/status<br/>conflict_reason]
    Unknown --> Output
    
    Output --> End([结束])
```

---

## 7. 上下文组装与裁剪流程图

```mermaid
flowchart LR
    subgraph Sources["上下文来源"]
        S1[历史纪要模板<br/>source=minutes<br/>优先级最高]
        S2[同类议题参考<br/>source!=minutes]
        S3[专业术语<br/>mapped_terms]
        S4[发言人列表<br/>resolved_speakers]
        S5[口水稿<br/>draft_text<br/>优先级最低]
    end

    subgraph Assembly["组装阶段"]
        A1["按优先级排序<br/>模板→议题→术语→发言人→口水稿"]
        A2["添加章节标记<br/>## 历史纪要模板\n..."]
    end

    subgraph Truncate["裁剪阶段"]
        T1["计算预算<br/>budget = context_token_budget<br/>* chars_per_token"]
        T2["顺序累加片段<br/>直到接近预算"]
        T3["最后片段截断<br/>添加...后缀"]
    end

    subgraph Prompt["Prompt构建"]
        P1[System Prompt<br/>角色定义+约束条件<br/>区分历史/本次]
        P2[User Prompt<br/>会议信息+上下文<br/>+JSON输出要求]
    end

    S1 --> A1
    S2 --> A1
    S3 --> A1
    S4 --> A1
    S5 --> A1
    
    A1 --> A2 --> T1 --> T2 --> T3 --> P1
    T3 --> P2
    
    P1 --> LLM[LLM生成]
    P2 --> LLM
```

---

## 8. 数据入库流水线图

```mermaid
flowchart TB
    subgraph Sources["数据源"]
        S1[会议纪要<br/>minutes]
        S2[附件文档<br/>attachment]
        S3[口水稿分段<br/>draft_segment]
        S4[MD文件<br/>VLM输出]
    end

    subgraph Validation["校验层"]
        V1["类型归一化<br/>decision→conclusion<br/>action_item→todo"]
        V2["规则校验<br/>todo必须有owner<br/>open_issue建议next_step"]
        V3["字段补全<br/>source/type/time/level1/level2"]
    end

    subgraph LLMGeneration["LLM字段生成<br/>Qwen3-30B-A3B"]
        L1["summary_short<br/>短摘要"]
        L2["keywords<br/>关键词"]
        L3["sentiment<br/>情感分析"]
        L4["importance<br/>重要性评分"]
        L5["category<br/>智能分类"]
        L6["decision_summary<br/>决策结论"]
    end

    subgraph Embedding["向量化"]
        E1[调用Embedding API<br/>text→4096维向量]
    end

    subgraph Milvus["Milvus存储"]
        M1["Collection: minutes"]
        M2["Schema Fields:<br/>基础: text/vector/source/type<br/>分类: level1/level2/topic<br/>时间: author/time/version<br/>待办: owner/deadline/status<br/>来源: source_id/source_position<br/>项目: project/department/organization<br/>扩展: sentiment/keywords/importance<br/>动态字段支持"]
    end

    S1 -->|ingest_minutes_chunks| V1
    S2 -->|ingest_attachments| V3
    S3 -->|ingest_draft_segments| V3
    S4 -->|md_ingest<br/>LLM分类| V3
    
    V1 --> V2 --> V3 --> LLMGeneration --> Embedding --> Milvus
```

---

## 9. 口水稿语义切分流程图

```mermaid
flowchart TD
    Start([开始]) --> Input[输入: draft_text<br/>topic_names]
    
    Input --> LLMSeg["LLM语义切分<br/>_semantic_segmentation"]
    
    LLMSeg --> Extract["提取JSON结果<br/>segments列表<br/>含topic/position/confidence"]
    
    Extract --> Validate[验证位置匹配<br/>文本对齐]
    
    Validate --> PostProcess["后处理<br/>_post_process_segments<br/>合并短段落/处理重叠"]
    
    PostProcess --> CalculateConf["计算置信度<br/>_calculate_confidence"]
    
    CalculateConf --> Classify{置信度判断}
    Classify -->|>=0.6| HighConf[高置信度段落<br/>segments]
    Classify -->|<0.6| LowConf[低置信度段落<br/>ambiguous_segments]
    
    HighConf --> Result
    LowConf --> Result[SegmentationResult]
    
    Result --> Output[输出: 段落列表<br/>模糊标记<br/>未分配文本]
    
    LLMSeg -.->|失败| Fallback["Fallback<br/>关键词切分"]
    Fallback --> Result
    
    Output --> End([结束])
```

---

## 10. Schema扩展管理流程图

```mermaid
flowchart TB
    subgraph Registration["字段注册"]
        R1[ExtensionFieldConfig<br/>field_name/type/description]
        R2[generation_method<br/>llm/rule/none]
        R3[generation_prompt<br/>rule_expression]
    end

    subgraph Generation["字段生成"]
        G1["LLM生成<br/>调用complete()"]
        G2["规则生成<br/>字段提取/切片"]
        G3["外部传入<br/>不生成"]
    end

    subgraph Migration["Schema迁移"]
        M1[source_collection]
        M2[target_collection<br/>enable_dynamic_field=True]
        M3[数据批量迁移]
    end

    subgraph Preview["预览功能"]
        P1[输入文本]
        P2[预览生成结果<br/>不写入DB]
    end

    R1 --> R2 --> R3 --> Registry[扩展字段注册表]
    
    Registry --> G1
    Registry --> G2
    Registry --> G3
    
    G1 --> Milvus[(Milvus存储<br/>动态字段)]
    G2 --> Milvus
    
    Registry --> Migration
    Migration --> Milvus
    
    Registry --> Preview
    P1 --> P2
```

---

## 11. 部署架构图

```mermaid
flowchart TB
    subgraph Client["客户端"]
        Web[Web应用]
        Mobile[移动端]
        OA[OA系统]
    end

    subgraph Gateway["网关层"]
        Nginx[Nginx反向代理]
    end

    subgraph API["API服务层"]
        FastAPI[FastAPI服务<br/>uvicorn]
        subgraph Service["smart_minutes模块"]
            Router[Router<br/>工具路由]
            Agent[MinutesAgent<br/>执行编排]
            Tools[Tools<br/>检索/映射/切分]
            SchemaMgmt[SchemaManagement<br/>扩展字段管理]
        end
    end

    subgraph Infrastructure["基础设施层"]
        Milvus[(Milvus<br/>向量数据库<br/>动态字段支持)]
        MySQL[(MySQL<br/>映射表/专有名词/元数据)]
        Redis[(Redis<br/>缓存)]
    end

    subgraph External["外部服务"]
        LLM[LLM API<br/>Qwen3-30B-A3B<br/>生成/分类/切分]
        Embedding[Embedding API<br/>4096维向量]
        FaceRec[(人脸/声纹<br/>识别服务)]
    end

    Web --> Nginx
    Mobile --> Nginx
    OA --> Nginx
    
    Nginx --> FastAPI
    FastAPI --> Service
    
    Service --> Milvus
    Service --> MySQL
    Service --> Redis
    Service --> LLM
    Service --> Embedding
    Service --> FaceRec
    
    %% 流式接口特殊配置
    Nginx -.->|proxy_buffering off<br/>SSE流式支持| FastAPI
```

---

## 12. 会议类型模板继承关系图

```mermaid
flowchart TB
    subgraph Global["全局默认"]
        G1[default_top_k: 5]
        G2[dense_weight: 0.5]
        G3[sparse_weight: 0.5]
        G4[context_token_budget: 8000]
    end

    subgraph Template["会议类型模板<br/>config/templates.yaml"]
        T1["周会模板<br/>top_k:3<br/>budget_multiplier:0.8"]
        T2["需求评审模板<br/>top_k:8<br/>budget_multiplier:1.2"]
        T3["其他类型..."]
    end

    subgraph Weights["分类型权重"]
        W1[todo_weights<br/>type_weight/dense_weight/sparse_weight]
        W2[open_issue_weights]
        W3[conclusion_weights]
    end

    subgraph Request["请求参数<br/>MinutesRequest.options"]
        R1[top_k]
        R2[dense_weight]
        R3[retrieval_weights<br/>按类型指定]
    end

    subgraph Merge["合并策略"]
        M["优先级: 请求 > 模板 > 全局默认<br/>_resolve_dense_sparse()"]
    end

    subgraph Result["最终参数"]
        F1[merged_top_k]
        F2[merged_dense_weight]
        F3[merged_retrieval_weights]
    end

    G1 --> Merge
    G2 --> Merge
    T1 --> Merge
    T2 --> Merge
    T1 --> W1
    T2 --> W2
    R1 --> Merge
    R2 --> Merge
    
    Merge --> Result
    
    Result --> Router[路由生成<br/>工具调用参数]
```

---

## 13. 错误处理与降级策略图

```mermaid
flowchart TD
    Start([工具执行]) --> Exec{执行是否成功?}
    
    Exec -->|成功| AddResult[添加结果到refs]
    Exec -->|失败| CheckSeverity{严重程度?}
    
    CheckSeverity -->|可恢复| Warning[记录warning<br/>继续执行]
    CheckSeverity -->|严重| Error[记录error<br/>标记partial=true]
    
    Warning --> Next{还有更多工具?}
    Error --> Next
    AddResult --> Next
    
    Next -->|是| Start
    Next -->|否| CheckLLM{LLM生成<br/>是否成功?}
    
    CheckLLM -->|成功| ParseJSON{解析JSON<br/>是否成功?}
    CheckLLM -->|失败| Fallback[返回占位内容<br/>+ errors]
    
    ParseJSON -->|成功| BuildOutput
    ParseJSON -->|失败| UseContent[使用原始内容<br/>structured部分为空]
    
    BuildOutput[构建完整响应<br/>含structured_output] --> CheckPartial{存在<br/>warnings/errors?}
    CheckPartial -->|是| MarkPartial[partial=true]
    CheckPartial -->|否| MarkFull[partial=false]
    
    Fallback --> Output
    UseContent --> Output
    MarkPartial --> Output[返回MinutesResponse]
    MarkFull --> Output
    
    Output --> End([结束])
```

---

## 14. API 功能总览

### 14.1 核心生成 API

| API 路径 | 方法 | 功能描述 |
|---------|------|---------|
| `/api/v1/smart-minutes/generate` | POST | 生成完整纪要 |
| `/api/v1/smart-minutes/retrieve` | POST | 仅检索，不调用LLM |
| `/api/v1/smart-minutes/generate-stream` | POST | 流式生成纪要 |
| `/api/v1/smart-minutes/ingest-from-md` | POST | MD文件解析入库 |

### 14.2 独立查询 API (9大功能)

| API 路径 | 底层工具 | 功能描述 |
|---------|---------|---------|
| `/api/v1/smart-minutes/query/series` | retrieve_latest_minutes_by_series | 同系列历史纪要 |
| `/api/v1/smart-minutes/query/by-topic` | retrieve_by_topic | 议题/相似议题历史 |
| `/api/v1/smart-minutes/query/by-person` | retrieve_by_person + resolve_oral_to_formal_candidates | 按人查询 |
| `/api/v1/smart-minutes/query/attachments` | get_attachments_by_meeting | 附件信息 |
| `/api/v1/smart-minutes/query/topic-from-draft` | retrieve_similar_topic_by_draft | 口水稿→议题名 |
| `/api/v1/smart-minutes/query/similar-todos-issues` | retrieve_similar_todos_or_issues | 类似待办/遗留 |
| `/api/v1/smart-minutes/query/similar-conclusions` | retrieve_similar_conclusions | 类似议题结论 |

### 14.3 映射与匹配 API

| API 路径 | 功能描述 |
|---------|---------|
| `/api/v1/smart-minutes/mappings/oral-names` | 批量添加口头称呼映射 |
| `/api/v1/smart-minutes/match-chunks-to-topics` | Chunk-主题匹配 |

### 14.4 专有名词 API

| API 路径 | 方法 | 功能描述 |
|---------|------|---------|
| `/api/v1/smart-minutes/extract-proper-nouns` | POST | 提取专有名词并存储 |
| `/api/v1/smart-minutes/proper-nouns` | GET | 查询专有名词列表 |

### 14.5 Schema 管理 API

| API 路径 | 方法 | 功能描述 |
|---------|------|---------|
| `/api/v1/schema/info/{collection_name}` | GET | 获取Schema信息 |
| `/api/v1/schema/register-field` | POST | 注册扩展字段 |
| `/api/v1/schema/registered-fields` | GET | 列出已注册字段 |
| `/api/v1/schema/register-field/{field_name}` | DELETE | 注销扩展字段 |
| `/api/v1/schema/generate-fields` | POST | 为存量数据生成字段 |
| `/api/v1/schema/migrate` | POST | Schema迁移 |
| `/api/v1/schema/preview-field-generation` | POST | 预览字段生成 |

---

## 15. Milvus Collection Schema 设计

### 15.1 基础字段 (固定)

| 字段名 | 类型 | 说明 |
|-------|------|------|
| pk | INT64 | 主键，自增 |
| text | VARCHAR(65535) | 文本内容 |
| vector | FLOAT_VECTOR(4096) | 向量嵌入 |

### 15.2 核心元数据字段

| 字段名 | 类型 | 说明 |
|-------|------|------|
| source | VARCHAR(64) | 来源：minutes/attachment/draft |
| type | VARCHAR(64) | 类型：summary/todo/open_issue/conclusion |
| level1 | VARCHAR(256) | 一级分类（会议类型） |
| level2 | VARCHAR(256) | 二级分类 |
| topic | VARCHAR(256) | 议题名 |
| author | VARCHAR(128) | 作者/发言人 |

### 15.3 时间与版本字段

| 字段名 | 类型 | 说明 |
|-------|------|------|
| time | VARCHAR(32) | 时间戳 |
| version | VARCHAR(32) | 版本号 |
| source_id | VARCHAR(256) | 来源ID（文档标识） |
| source_position | VARCHAR(256) | 来源位置 |

### 15.4 待办相关字段

| 字段名 | 类型 | 说明 |
|-------|------|------|
| owner | VARCHAR(128) | 待办负责人 |
| deadline | VARCHAR(32) | 截止时间 |
| status | VARCHAR(32) | 状态 |

### 15.5 项目维度字段

| 字段名 | 类型 | 说明 |
|-------|------|------|
| project | VARCHAR(128) | 项目名 |
| department | VARCHAR(128) | 部门 |
| organization | VARCHAR(128) | 组织 |

### 15.6 扩展字段 (动态)

| 字段名 | 类型 | 生成方式 |
|-------|------|---------|
| summary_short | VARCHAR | LLM生成 |
| summary_detailed | VARCHAR | LLM生成 |
| keywords | JSON | LLM生成 |
| sentiment | VARCHAR | LLM生成 |
| importance | INT | LLM生成 |
| category | VARCHAR | LLM生成 |
| decision_summary | VARCHAR | LLM生成 |
| action_items_structured | JSON | LLM生成 |

---

*文档版本: 2026-03-03*  
*对应代码版本: smart_minutes v2.0*  
*更新内容: 新增Schema管理、动态字段、LLM字段生成、专有名词存储、口水稿语义切分*
