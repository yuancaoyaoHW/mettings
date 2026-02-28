# 智能会议纪要产品/技术需求（可落地版）

## 1. 业务目标与核心产出

目标：利用本次会议多模态记录（口水稿/音视频）叠加历史纪要、附件知识、人员画像，自动生成高质量会议纪要，满足：

- 格式统一：沿用同系列会议模板；
- 内容延续：复用同议题历史结论、遗留问题、行动项风格；
- 要素对齐：人、事、议题、附件可关联；
- 可追溯：不确定信息带来源与置信度。

核心产出为结构化纪要（兼容文本纪要）：

- `meeting_info`：会议基本信息；
- `topics[]`：议题摘要、要点、结论、遗留、待办；
- `materials[]`：附件/历史引用片段；
- `traceability`：历史纪要 ID、附件定位、speaker 置信度。

## 2. 输入维度与检索问题

### 2.1 会议上下文

输入：`meeting_type`/`meeting_name`/`project`/`department`/`organization`

能力：

- 同系列会议召回（Top-K）；
- 模板来源会议确定（Top-1 默认模板）；
- 同会系列附件入口与术语映射召回。

规则：

- 同系列优先级：类型 + 规范化名称主干 + 组织属性 + 时间；
- 时间按 `time` 倒序。

### 2.2 议题上下文

输入：`topics[]` 或 `draft_text`

能力：

- 按议题检索历史总结/结论/遗留/待办；
- 按议题检索附件；
- 口水稿切分到议题段。

### 2.3 发言人识别

输入：`realtime_speaker.face_result`、`voice_result`、`venue_name`

能力：

- 多模态候选融合；
- 输出归属人、置信度、候选列表；
- 冲突时输出 `status=conflict` 供人工纠正。

### 2.4 按人检索历史

输入：`person_names[]` 与口头称呼 `oral_names[]`

能力：

- 口头称呼映射正式人名；
- 按人检索其历史纪要片段；
- 支撑 owner 候选和行动项风格延续。

## 3. 关键流水线（6 模块）

1. Meeting Resolver：同系列会议/模板/附件集合；
2. Speaker Fusion：多模态融合归属；
3. Transcript Structuring：口水稿按议题切分；
4. Topic Retrieval/RAG：议题相关历史召回；
5. Attachment Search：议题附件片段召回；
6. Draft Generator：基于模板与召回内容生成纪要。

## 4. 检索与匹配规则

### 4.1 同系列会议

- 强约束：会议类型、组织属性；
- 次强约束：名称主干（去日期/编号）；
- 弱约束：参会人重叠；
- 排序：时间优先 + 相关性。

### 4.2 相似议题

- 语义相似 + 关键词重叠 + 同系列加权；
- 产出“历史议题片段包 + 风格特征”。

### 4.3 分类型索引

- `todo/open_issue/conclusion` 分 type 检索；
- 每类独立 top_k 与权重，提升召回精度；
- 支持权重参数（`dense_weight/sparse_weight/type_weight`）透传；
- `todo + open_issue` 支持双路召回后融合排序（按加权 score 取 Top-K）。

## 5. 数据与工程约束

### 5.1 主数据与映射

- 称呼别名映射：`oral_name -> formal_name -> employee_id`
- 专业术语映射：缩写/同义词 -> 标准术语
- 会议议题元数据：会议系列、项目、部门、时间、议题标签

### 5.2 Milvus 数据约定

- 通用字段：`text/vector/source/type/level1/level2/topic/author/time/version`
- 追溯字段：`source_id/source_position/confidence`
- 可选组织字段：`project/department/organization`
- 分索引字段：`owner/deadline/status/next_step/issue_reason`

### 5.3 生成约束

- 严格区分“历史背景”和“本次新结论”；
- 关键事实优先附来源；
- 响应允许部分成功，返回 `warnings/errors/partial`。

## 6. 风险与对策

- Speaker 冲突：输出候选与冲突状态，允许人工回写；
- 议题切分不稳定：保留不确定提示，允许校对；
- 历史幻觉继承：Prompt 约束 + 输出追溯；
- 附件版本与权限：引用绑定版本/位置，按权限过滤。

## 7. 验收标准

- 结构完整率：结构化字段齐全比例；
- 模板一致性：同系列纪要结构与措辞一致性；
- 检索命中率：Top-K 命中人工标注答案；
- 发言人准确率：准确率/冲突率/未知占比；
- 可追溯覆盖率：结论与关键事实附来源的覆盖比例。

