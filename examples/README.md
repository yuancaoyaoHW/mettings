# Qwen3-30B-A3B 智能纪要系统使用指南

本目录包含针对自部署 Qwen3-30B-A3B 大模型的配置和演示脚本。

## 快速开始

### 1. 配置环境变量

复制生产环境配置模板：

```bash
cp .env.qwen3-production .env
```

编辑 `.env` 文件，配置你的 Qwen3-30B-A3B 服务地址：

```bash
# 修改为你的实际服务地址
LLM_BASE_URL=http://your-qwen3-server:8000/v1
LLM_MODEL_NAME=Qwen3-30B-A3B
```

### 2. 测试连接

```bash
python examples/test_qwen3_api.py
```

### 3. 运行完整演示

```bash
python examples/qwen3_full_demo.py
```

## 脚本说明

| 脚本 | 用途 | 运行时间 |
|------|------|----------|
| `test_qwen3_api.py` | API 连接测试和基准测试 | ~2 分钟 |
| `qwen3_demo.py` | 基础功能演示 | ~1 分钟 |
| `qwen3_full_demo.py` | 完整功能演示（推荐） | ~3 分钟 |

## Qwen3-30B-A3B 部署建议

### 硬件配置

| 场景 | GPU 配置 | 并发能力 | 延迟 |
|------|----------|----------|------|
| 开发测试 | A100 40G x 1 | 1-2 | 500ms |
| 生产环境 | A100 80G x 2 | 4-8 | 300ms |
| 大规模生产 | A100 80G x 4 | 8-16 | 200ms |

### 部署框架选择

推荐使用 vLLM 部署，支持高并发和连续批处理：

```bash
# vLLM 部署示例
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen3-30B-A3B \
    --tensor-parallel-size 2 \
    --max-num-seqs 8 \
    --max-model-len 32768
```

### 性能优化

1. **启用 Continuous Batching**: 提高 GPU 利用率
2. **使用 FP16 量化**: 平衡精度和性能
3. **调整 max-num-seqs**: 根据并发需求设置
4. **预热模型**: 启动后先运行几个测试请求

## 配置说明

### 关键环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_BASE_URL` | Qwen3 服务地址 | `http://localhost:8000/v1` |
| `LLM_MODEL_NAME` | 模型名称 | `Qwen3-30B-A3B` |
| `LLM_API_KEY` | API Key（自部署可留空） | `sk-local` |
| `ENABLE_LLM_FIELD_GENERATION` | 启用 LLM 字段生成 | `true` |
| `LLM_GENERATION_WORKERS` | 并发数 | `4` |

### 入库参数

```python
from pipelines.ingest import ingest_minutes_chunks

# 自部署模型场景：启用 LLM 字段生成
rows = ingest_minutes_chunks(
    chunks,
    use_llm_for_fields=True,  # 使用 Qwen3 生成扩展字段
    enable_dynamic_fields=True
)
```

## 扩展字段列表

使用 Qwen3-30B-A3B 自动生成的字段：

| 字段名 | 类型 | 说明 | 生成方式 |
|--------|------|------|----------|
| `summary_short` | string | 短摘要（50字） | LLM |
| `summary_detailed` | string | 详细摘要（200字） | LLM |
| `keywords` | array | 关键词（最多5个） | LLM |
| `sentiment` | string | 情感倾向 | LLM |
| `importance` | int | 重要性评分（1-5） | LLM |
| `category` | string | 业务分类 | LLM |
| `action_items_structured` | array | 结构化行动项 | LLM |
| `decision_summary` | string | 决策结论提取 | LLM |

## 故障排查

### 连接失败

```bash
# 检查服务是否运行
curl http://your-qwen3-server:8000/v1/models

# 检查环境变量
echo $LLM_BASE_URL
echo $LLM_MODEL_NAME
```

### 生成速度慢

- 检查 GPU 利用率：`nvidia-smi`
- 调整并发数：`LLM_GENERATION_WORKERS`
- 考虑模型量化：INT8 比 FP16 快 2 倍

### 生成质量不佳

- 检查 prompt 模板：`pipelines/ingest.py`
- 调整 temperature：当前为 0.3，可适当降低
- 增加 max_tokens：确保输出不被截断

## 升级指南

### 从 API 模型切换到自部署

1. 部署 Qwen3-30B-A3B 服务
2. 更新 `.env` 配置
3. 设置 `ENABLE_LLM_FIELD_GENERATION=true`
4. 运行测试脚本验证

### 模型版本升级

更新 `LLM_MODEL_NAME` 为新版本名称，重启服务即可。

## 技术支持

如有问题，请检查：
1. Qwen3 服务日志
2. 本项目的 `logs/smart_minutes.log`
3. Milvus 连接状态
