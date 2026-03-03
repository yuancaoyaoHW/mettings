"""
自动化测试与评测模块

提供：
- 检索命中率评测
- 生成质量评测
- 端到端测试
- 性能基准测试
"""
from tests.evaluation.retrieval_eval import RetrievalEvaluator
from tests.evaluation.generation_eval import GenerationEvaluator
from tests.evaluation.end_to_end import EndToEndTester

__all__ = [
    "RetrievalEvaluator",
    "GenerationEvaluator", 
    "EndToEndTester",
]
