# 智能会议纪要

基于 LLM Agent 的智能会议纪要模块：历史纪要检索、模板与动态 Prompt 生成、发言人融合、映射与附件检索等。

## 技术栈

- Python 3.10+
- Milvus（向量检索）
- LangChain（Agent 编排）

## 项目结构（规划）

```
smart_minutes/     # 智能纪要独立功能包
pipelines/         # 数据入库与向量化
api/               # 对外 API
```

详见项目计划文档。

## 开发

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## License

Private / 内部使用
