# 智能会议纪要

基于 LLM Agent 的智能会议纪要模块：历史纪要检索、模板与动态 Prompt 生成、发言人融合、映射与附件检索等。

## 文档

- **[对接手册](docs/INTEGRATION.md)**：进程内/HTTP 对接、依赖注入、与现有 Milvus 对接要点、数据约定
- **[使用指南](docs/USAGE.md)**：快速开始、请求与响应、环境变量、能力与输入对应、常见问题

## 技术栈

- Python 3.10+
- Milvus（向量检索）
- LangChain（Agent 编排）

## 项目结构

```
smart_minutes/     # 智能纪要独立功能包（门面 + 契约 + Agent + 工具）
pipelines/         # 数据入库与向量化
api/               # FastAPI：/api/smart-minutes/generate、/retrieve、/generate-stream
config/            # 配置
data/              # 数据模型
services/          # 共享能力（embedding、llm）
```

## 执行流程图

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

## 组件架构图

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

## 开发

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn api.main:app --reload   # 启动 API
```

## Linux 子模块部署
 
 如果你将本仓库作为 Git Submodule 或子目录放置在主工程的 `src/service/smart_minutes` 下，并希望独立启动 HTTP 服务：
 
 ```bash
 # 假设在主工程根目录
 export PYTHONPATH=$(pwd)
 
 # 启动服务（建议用 Systemd 或 Supervisor 管理）
 uvicorn src.service.smart_minutes.api.main:app --host 0.0.0.0 --port 18080
 ```
 
 若需通过 Nginx 反向代理流式接口，请务必关闭缓冲：
 
 ```nginx
 location /api/smart-minutes/generate-stream {
     proxy_pass http://127.0.0.1:18080;
     proxy_buffering off;  # 关键：否则 SSE 会被缓冲
     proxy_cache off;
 }
 ```
 
 ## License

Private / 内部使用
