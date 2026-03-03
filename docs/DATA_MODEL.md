# 数据模型

Milvus 集合字段说明、MySQL 表与用途。

---

## 一、Milvus 集合

### 核心字段（与 9 大功能相关）

| 字段 | 类型 | 说明 |
|------|------|------|
| pk | INT64 | 主键 |
| text | VARCHAR | 文本内容 |
| vector | FLOAT_VECTOR | 向量（dim=768） |
| source | VARCHAR | 来源：minutes / draft / attachment |
| type | VARCHAR | 类型：todo / open_issue / conclusion / summary 等 |
| topic | VARCHAR | 议题名 |
| author | VARCHAR | 发言人正式名 |
| owner | VARCHAR | 负责人（待办） |
| source_id | VARCHAR | 来源文档/会议 ID |
| source_position | VARCHAR | 在源文档中的位置 |

### 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| level1 | VARCHAR | 会议类型/名称（同系列过滤） |
| level2 | VARCHAR | 二级分类 |
| time | VARCHAR | 时间戳（同系列排序） |
| version | VARCHAR | 版本 |
| deadline | VARCHAR | 截止时间 |
| status | VARCHAR | 状态 |

### 动态字段

若启用 `enable_dynamic_field`，可扩展：`summary_short`、`keywords`、`sentiment`、`importance`、`category` 等。

---

## 二、MySQL 表

### oral_name_mapping

口头称呼→正式人名映射。

| 字段 | 说明 |
|------|------|
| oral_name | 口头称呼 |
| formal_name | 正式人名 |
| employee_id | 员工 ID |
| confidence | 置信度 |
| is_active | 是否启用 |

### professional_terms

专业术语（带解释、别名、会议类型关联）。

| 字段 | 说明 |
|------|------|
| term | 标准术语 |
| aliases | 别名列表 |
| description | 解释 |
| meeting_types | 适用会议类型 |

### proper_nouns

专有名词（**仅提取不解释**，按知识库存储）。与 `professional_terms` 区分。

| 字段 | 说明 |
|------|------|
| kb_name | 知识库名 |
| collection_name | Milvus 集合名 |
| term | 专有名词 |
| source_doc | 来源文档 |
| source_id | 来源 ID |

### meeting_type_terms

会议类型与专业术语关联。

### attachments / attachment_chunks

附件元数据及与 Milvus chunk 的关联。

### meeting_templates

会议模板配置。

---

## 三、oral_name_mapping 与 proper_nouns 区别

| 维度 | oral_name_mapping | proper_nouns |
|------|-------------------|--------------|
| 用途 | 口头称呼→正式人名、发言人解析 | 专有名词列表（人名、术语、产品名等） |
| 存储 | 按映射表，一对多支持 | 按知识库，仅提取不解释 |
| 查询 | resolve_oral_to_formal、resolve_oral_to_formal_candidates | list_by_kb |
