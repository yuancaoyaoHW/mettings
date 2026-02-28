# 智能会议纪要系统 - 详细架构图

## 1. 整体数据流架构图

```mermaid
flowchart TB
    subgraph Input["输入层"]
        I1[会议类型/名称<br/>meeting_type/name]
        I2[议题列表<br/>topics[]]
        I3[口水稿<br/>draft_text]
        I4[多模态输入<br/>人脸/声纹/会场]
        I5[口头称呼<br/>oral_names[]]
        I6[待办/结论<br/>open_issues/conclusions]
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
        T4["口水稿切分 (draft)<br/>按议题分段"]
        T5["发言人融合 (speaker)<br/>多模态融合"]
    end

    subgraph Agent["Agent编排 (agents/minutes_agent.py)"]
        A1[分组执行<br/>Group1顺序→Group2并行→Group3顺序]
        A2[结果汇总<br/>refs + speakers + terms]
        A3[上下文组装<br/>模板+历史+片段+术语]
        A4[预算裁剪<br/>context_token_budget]
        A5[LLM生成<br/>结构化输出]
    end

    subgraph Output["输出层"]
        O1[纪要正文<br/>minutes_content]
        O2[结构化数据<br/>structured_output]
        O3[追溯信息<br/>references + traceability]
        O4[诊断信息<br/>warnings + errors + partial]
    end

    Input --> Router
    Router --> Tools
    Tools --> Agent
    Agent --> Output
```

---

## 2. 模块依赖关系图

```mermaid
flowchart LR
    subgraph External["外部依赖"]
        Milvus[(Milvus<br/>向量存储)]
        LLM[(LLM API<br/>生成服务)]
        Embed[(Embedding API)]
        MySQL[(MySQL/Redis<br/>映射表)]
        FaceAPI[(人脸/声纹API)]
    end

    subgraph Contracts["契约层 (contracts.py)"]
        I1[IRetrieval]
        I2[IMappingStore]
        I3[ISpeakerResolver]
    end

    subgraph Adapters["适配器层 (adapters/)"]
        A1[RetrievalAdapter]
        A2[MappingStoreAdapter]
        A3[SpeakerResolverAdapter]
    end

    subgraph Core["核心层"]
        direction TB
        Schemas[(schemas.py<br/>Pydantic模型)]
        Config[(config.py<br/>配置管理)]
        Templates[(config_templates.py<br/>模板策略)]
        
        subgraph Agents["Agent层 (agents/)"]
            Router[router.py<br/>工具路由]
            MinutesAgent[minutes_agent.py<br/>执行编排]
        end
        
        subgraph Tools["工具层 (tools/)"]
            Rag[rag.py<br/>检索封装]
            Attach[attachment.py<br/>附件]
            Speaker[speaker.py<br/>发言人]
            Map[mapping.py<br/>映射]
            Draft[draft.py<br/>口水稿]
        end
    end

    subgraph API["接口层"]
        Service[SmartMinutesService<br/>进程内门面]
        HTTP[FastAPI<br/>HTTP服务]
    end

    subgraph Pipeline["数据流水线 (pipelines/)"]
        Ingest[ingest.py<br/>入库与校验]
    end

    %% 依赖关系
    Adapters --> Contracts
    A1 --> Milvus
    A2 --> MySQL
    A3 --> FaceAPI
    
    Tools --> Contracts
    Rag --> I1
    Attach --> I1
    Speaker --> I3
    Map --> I2
    
    Agents --> Tools
    Agents --> Schemas
    Agents --> Config
    
    Service --> Agents
    Service --> Contracts
    HTTP --> Service
    
    Ingest --> Embed
    Ingest --> Milvus
    
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
    
    Note over Router: 参数合并优先级：<br/>请求options > meeting_type模板 > 全局默认
    
    Router->>Router: 解析retrieval_weights
    Router->>Router: 生成工具调用序列
    Router-->>Service: tool_suggestions[]
    
    Service->>Agent: run(request, tool_suggestions)
    
    Note over Agent: Group1: 映射工具（顺序）
    Agent->>Tools: mapping (oral→formal)
    Tools-->>Agent: mapped_terms[]
    Agent->>Tools: professional_terms
    Tools-->>Agent: terms[]
    
    Note over Agent: Group2: 检索工具（并行）
    par 并行执行
        Agent->>Tools: retrieve_latest_minutes_by_series
        Tools-->>Agent: series_refs[]
    and
        Agent->>Tools: retrieve_by_topic
        Tools-->>Agent: topic_refs[]
    and
        Agent->>Tools: retrieve_by_person
        Tools-->>Agent: person_refs[]
    and
        Agent->>Tools: retrieve_similar_todos_or_issues
        Tools-->>Agent: todo_issue_refs[]
    and
        Agent->>Tools: retrieve_similar_conclusions
        Tools-->>Agent: conclusion_refs[]
    and
        Agent->>Tools: search_attachments_by_topic
        Tools-->>Agent: attachment_refs[]
    end
    
    Note over Agent: Group3: 后处理工具（顺序）
    Agent->>Tools: get_draft_segments_by_topics
    Tools-->>Agent: segments[]
    
    opt 有实时发言人输入
        Agent->>Tools: resolve_speaker<br/>(face/voice/venue)
        Tools-->>Agent: SpeakerResolution
    end
    
    Agent->>Agent: 结果汇总与去重
    Agent->>Agent: 组装上下文context
    Agent->>Agent: _truncate_to_budget<br/>(按token预算裁剪)
    
    Agent->>Agent: _build_prompts<br/>构建system/user prompt
    
    Agent->>LLM: 调用生成
    LLM-->>Agent: minutes_content
    
    Agent->>Agent: _build_structured_output<br/>构造结构化结果
    
    Agent-->>Service: MinutesResponse
    Service-->>API: MinutesResponse
    API-->>Client: JSON响应
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
    
    MinutesRequest {
        string meeting_type
        string meeting_name
        string project
        string department
        string organization
        string draft_text
        array topics
        array person_names
        array oral_names
        array open_issues
        array conclusions
        object options
    }
    
    TopicSection {
        string topic_name
        string summary
        array key_points
        array conclusions
        array open_issues
        array action_items
        array source_ref_ids
        float confidence
    }
    
    ActionItem {
        string content
        string owner
        string deadline
        string status
        array source_ref_ids
    }
    
    ReferenceItem {
        int pk
        float score
        string page_content
        string source
        string topic
        string author
        string time
        string source_id
        string source_position
        float confidence
    }
    
    SpeakerResolution {
        string resolved_name
        float confidence
        array candidates
        string status
        string conflict_reason
    }
    
    TraceabilityInfo {
        array history_minutes_ids
        array attachment_positions
        array speaker_resolution
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
    end

    subgraph Weights["权重配置"]
        W1[type_weight<br/>类型权重]
        W2[dense_weight<br/>向量权重]
        W3[sparse_weight<br/>关键词权重]
    end

    subgraph Strategy["检索策略"]
        S1["同系列会议<br/>retrieve_latest_minutes_by_series"]
        S2["按议题检索<br/>retrieve_by_topic"]
        S3["按人检索<br/>retrieve_by_person"]
        S4["待办/遗留双路<br/>retrieve_similar_todos_or_issues"]
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
    M3 --> References[references[]
    带score/confidence/source]
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
    
    CheckEmpty -->|是| Unknown[返回 unknown<br/>confidence=0]
    CheckEmpty -->|否| Sort[按confidence排序]
    
    Sort --> GetTop[取top候选]
    
    GetTop --> CheckTop2{存在top2且<br/>name不同且<br/>conf差<0.15?}
    
    CheckTop2 -->|是| Conflict[status=conflict<br/>conflict_reason=face_voice_close]
    CheckTop2 -->|否| CheckLowConf{top.confidence<0.5?}
    
    Conflict --> Output
    CheckLowConf -->|是| Unknown
    CheckLowConf -->|否| Resolved[status=resolved]
    
    Resolved --> Output[返回 SpeakerResolution<br/>resolved_name<br/>confidence<br/>candidates[]<br/>status]
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
        P1[System Prompt<br/>角色定义+约束条件]
        P2[User Prompt<br/>会议信息+上下文]
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
    end

    subgraph Validation["校验层"]
        V1["类型归一化<br/>decision→conclusion<br/>action_item→todo"]
        V2["规则校验<br/>todo必须有owner<br/>open_issue建议next_step"]
        V3["字段补全<br/>source/type/time"]
    end

    subgraph Embedding["向量化"]
        E1[调用Embedding API<br/>text→4096维向量]
    end

    subgraph Milvus["Milvus存储"]
        M1["Collection: minutes"]
        M2["Schema Fields:<br/>text/vector/source/type<br/>level1/level2/topic<br/>author/time/version<br/>owner/deadline/status<br/>source_id/source_position<br/>project/department/organization"]
    end

    S1 -->|ingest_minutes_chunks| V1
    S2 -->|ingest_attachments| V3
    S3 -->|ingest_draft_segments| V3
    
    V1 --> V2 --> V3 --> E1 --> Milvus
```

---

## 9. 部署架构图

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
            Router[Router]
            Agent[MinutesAgent]
            Tools[Tools]
        end
    end

    subgraph Infrastructure["基础设施层"]
        Milvus[(Milvus<br/>向量数据库)]
        MySQL[(MySQL<br/>映射表/元数据)]
        Redis[(Redis<br/>缓存)]
    end

    subgraph External["外部服务"]
        LLM[LLM API<br/>OpenAI/国产模型]
        Embedding[Embedding API]
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

## 10. 会议类型模板继承关系图

```mermaid
flowchart TB
    subgraph Global["全局默认"]
        G1[default_top_k: 5]
        G2[dense_weight: 0.5]
        G3[sparse_weight: 0.5]
        G4[context_token_budget: 8000]
    end

    subgraph Template["会议类型模板<br/>config/templates.yaml"]
        T1["周会模板"]
        T2["需求评审模板"]
        T3["其他类型..."]
    end

    subgraph Request["请求参数<br/>MinutesRequest.options"]
        R1[top_k]
        R2[dense_weight]
        R3[retrieval_weights]
    end

    subgraph Merge["合并策略"]
        M["优先级: 请求 > 模板 > 全局默认"]
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
    R1 --> Merge
    R2 --> Merge
    
    Merge --> Result
    
    Result --> Router[路由生成<br/>工具调用参数]
```

---

## 11. 错误处理与降级策略图

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
    
    CheckLLM -->|成功| BuildOutput[构建完整响应]
    CheckLLM -->|失败| Fallback[返回占位内容<br/>+ errors]
    
    BuildOutput --> CheckPartial{存在<br/>warnings/errors?}
    CheckPartial -->|是| MarkPartial[partial=true]
    CheckPartial -->|否| MarkFull[partial=false]
    
    Fallback --> Output
    MarkPartial --> Output
    MarkFull --> Output[返回MinutesResponse]
    
    Output --> End([结束])
```

---

*文档版本: 2026-02-28*
*对应代码版本: smart_minutes v1.0*
