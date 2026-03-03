# 变更日志

所有重要的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- 新增 MD 文件入库接口 `POST /api/v1/smart-minutes/ingest-from-md`
- 新增 `SmartMinutesService.ingest_from_md()` 方法支持 Markdown 文件解析入库
- 新增 `schema_management` 模块，支持扩展字段注册、生成、迁移与预览
- 新增 `MilvusClient` 完整封装，支持连接池、动态字段、批量操作
- 新增 `RetrievalAdapter` 动态字段过滤支持
- 新增 `SemanticDraftSegmenter` 完整实现，使用 Qwen3-30B-A3B 进行语义理解

### Changed
- 优化 `implementation_tracking.md` 进度至 85%
- 完善文档，补充 Schema 管理和扩展字段说明
- 优化 RAG 检索权重参数透传机制
- 改进参会人重叠度计算逻辑

### Fixed
- 修复 `plan_issues_analysis.md` 中部分问题状态未更新
- 完善 `minutes_agent.py` 中结构化输出解析逻辑

## [0.1.0] - 2026-02-28

### Added
- **核心功能**：智能会议纪要生成，支持结构化输出
- **检索能力**：
  - 同系列会议召回（Top-K）
  - 按议题检索历史总结/结论/遗留/待办
  - 按人检索历史纪要
  - 分类型检索（todo/open_issue/conclusion）支持权重参数透传
  - 口水稿语义切分（使用 LLM）
- **发言人融合**：支持人脸/声纹/会场多模态融合，返回置信度和冲突状态
- **映射功能**：口头称呼→正式人名、会议类型→专业术语
- **模板系统**：支持 meeting_type 级别的策略模板（JSON/YAML）
- **入库流水线**：支持 type 归一化、规则校验、动态字段生成
- **API 接口**：
  - `POST /api/v1/smart-minutes/generate` - 生成纪要
  - `POST /api/v1/smart-minutes/generate-stream` - 流式生成（SSE）
  - `POST /api/v1/smart-minutes/retrieve` - 仅检索
- **适配器实现**：
  - `RetrievalAdapter` - Milvus 检索封装
  - `MappingStoreAdapter` - 内存映射存储
  - `SpeakerResolverAdapter` - 发言人融合
  - `MappingStoreMySQL` - MySQL 映射持久化
- **测试覆盖**：RAG 工具测试、Agent 测试、Router 测试、端到端测试

### Technical Details
- 基于 Python 3.10+
- 使用 Pydantic v2 进行数据验证
- 使用 LangChain 进行 Agent 编排
- Milvus 2.3+ 向量数据库
- 支持 Qwen3-30B-A3B 自部署模型

### Documentation
- `README.md` - 项目概述和快速开始
- `docs/requirements_smart_minutes.md` - 完整需求规格
- `docs/implementation_tracking.md` - 实现进度追踪
- `docs/INTEGRATION.md` - 对接手册
- `docs/USAGE.md` - 使用指南
- `docs/architecture_diagrams.md` - 详细架构图
- `docs/HIGH_PRIORITY_IMPLEMENTATION_COMPLETE.md` - 高优先级功能完成报告
- `docs/plan_issues_analysis.md` - 问题分析

[Unreleased]: https://github.com/yourusername/mettings/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/mettings/releases/tag/v0.1.0
