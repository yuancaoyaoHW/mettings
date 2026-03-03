"""
检索命中率评测

评估指标：
- Recall@K：Top-K 中命中相关文档的比例
- MRR：平均倒数排名
- NDCG：归一化折损累积增益
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from smart_minutes import SmartMinutesService
from smart_minutes.schemas import MinutesRequest

logger = logging.getLogger(__name__)


@dataclass
class RetrievalExample:
    """检索评测样例"""
    query: str  # 查询文本
    topic: str  # 议题
    relevant_ids: List[str]  # 相关文档ID
    meeting_type: str = ""
    meeting_name: str = ""


@dataclass
class RetrievalMetrics:
    """检索指标"""
    recall_at_1: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    mrr: float = 0.0  # Mean Reciprocal Rank
    ndcg_at_5: float = 0.0
    ndcg_at_10: float = 0.0
    avg_latency_ms: float = 0.0
    total_queries: int = 0


class RetrievalEvaluator:
    """
    检索命中率评测器
    
    使用人工标注的查询-相关文档对进行评测
    """
    
    def __init__(self, service: SmartMinutesService):
        self.service = service
        self.examples: List[RetrievalExample] = []
    
    def load_dataset(self, dataset_path: str) -> int:
        """
        加载评测数据集
        
        数据集格式（JSON）：
        [
          {
            "query": "需求评审结论",
            "topic": "需求评审",
            "relevant_ids": ["minutes_001", "minutes_003"],
            "meeting_type": "产品周会"
          }
        ]
        """
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.examples = []
            for item in data:
                self.examples.append(RetrievalExample(
                    query=item.get("query", ""),
                    topic=item.get("topic", ""),
                    relevant_ids=item.get("relevant_ids", []),
                    meeting_type=item.get("meeting_type", ""),
                    meeting_name=item.get("meeting_name", "")
                ))
            
            logger.info(f"Loaded {len(self.examples)} evaluation examples")
            return len(self.examples)
            
        except Exception as e:
            logger.error(f"Failed to load dataset: {e}")
            return 0
    
    def evaluate(self, k_values: List[int] = [1, 5, 10]) -> RetrievalMetrics:
        """
        执行评测
        """
        import time
        
        if not self.examples:
            logger.warning("No evaluation examples loaded")
            return RetrievalMetrics()
        
        metrics = RetrievalMetrics(total_queries=len(self.examples))
        
        # 统计
        recall_at_k = {k: 0 for k in k_values}
        mrr_sum = 0.0
        ndcg_at_k = {k: 0.0 for k in k_values if k <= 10}
        total_latency = 0.0
        
        for example in self.examples:
            # 执行检索
            start_time = time.time()
            
            request = MinutesRequest(
                meeting_type=example.meeting_type,
                meeting_name=example.meeting_name,
                topics=[example.topic],
                draft_text=example.query,
            )
            
            response = self.service.run(request, retrieve_only=True)
            latency = (time.time() - start_time) * 1000
            total_latency += latency
            
            # 获取检索结果ID
            retrieved_ids = []
            for ref in response.references:
                source_id = ref.source_id or str(ref.pk)
                retrieved_ids.append(source_id)
            
            # 计算指标
            # Recall@K
            for k in k_values:
                if self._calculate_recall(retrieved_ids[:k], example.relevant_ids) > 0:
                    recall_at_k[k] += 1
            
            # MRR
            rank = self._get_first_relevant_rank(retrieved_ids, example.relevant_ids)
            if rank > 0:
                mrr_sum += 1.0 / rank
            
            # NDCG
            for k in ndcg_at_k.keys():
                ndcg_at_k[k] += self._calculate_ndcg(
                    retrieved_ids[:k], 
                    example.relevant_ids
                )
        
        # 计算平均值
        n = len(self.examples)
        metrics.recall_at_1 = recall_at_k[1] / n if 1 in recall_at_k else 0
        metrics.recall_at_5 = recall_at_k[5] / n if 5 in recall_at_k else 0
        metrics.recall_at_10 = recall_at_k[10] / n if 10 in recall_at_k else 0
        metrics.mrr = mrr_sum / n
        metrics.ndcg_at_5 = ndcg_at_k[5] / n if 5 in ndcg_at_k else 0
        metrics.ndcg_at_10 = ndcg_at_k[10] / n if 10 in ndcg_at_k else 0
        metrics.avg_latency_ms = total_latency / n
        
        return metrics
    
    def _calculate_recall(
        self,
        retrieved: List[str],
        relevant: List[str]
    ) -> float:
        """计算 Recall"""
        if not relevant:
            return 0.0
        
        retrieved_set = set(retrieved)
        relevant_set = set(relevant)
        
        hits = len(retrieved_set & relevant_set)
        return hits / len(relevant_set)
    
    def _get_first_relevant_rank(
        self,
        retrieved: List[str],
        relevant: List[str]
    ) -> int:
        """获取第一个相关文档的排名"""
        relevant_set = set(relevant)
        
        for i, doc_id in enumerate(retrieved, 1):
            if doc_id in relevant_set:
                return i
        return 0
    
    def _calculate_ndcg(
        self,
        retrieved: List[str],
        relevant: List[str],
        k: int = 10
    ) -> float:
        """计算 NDCG@K"""
        if not relevant:
            return 0.0
        
        # DCG
        dcg = 0.0
        relevant_set = set(relevant)
        
        for i, doc_id in enumerate(retrieved[:k], 1):
            if doc_id in relevant_set:
                # 相关性分数：在 relevant 列表中的位置决定
                rel = len(relevant) - relevant.index(doc_id)
                dcg += (2 ** rel - 1) / (i + 1)
        
        # IDCG（理想情况）
        idcg = 0.0
        for i in range(min(len(relevant), k)):
            rel = len(relevant) - i
            idcg += (2 ** rel - 1) / (i + 2)
        
        return dcg / idcg if idcg > 0 else 0.0
    
    def generate_report(self, metrics: RetrievalMetrics) -> str:
        """生成评测报告"""
        report = f"""
=== 检索命中率评测报告 ===

评测样本数: {metrics.total_queries}
平均延迟: {metrics.avg_latency_ms:.2f}ms

指标结果:
  Recall@1:  {metrics.recall_at_1:.3f}
  Recall@5:  {metrics.recall_at_5:.3f}
  Recall@10: {metrics.recall_at_10:.3f}
  MRR:       {metrics.mrr:.3f}
  NDCG@5:    {metrics.ndcg_at_5:.3f}
  NDCG@10:   {metrics.ndcg_at_10:.3f}

解读:
- Recall@K: Top-K 结果中命中相关文档的比例
- MRR: 平均倒数排名，越高表示相关文档排名越靠前
- NDCG: 考虑排序位置的相关性指标

===========================
"""
        return report


def create_sample_dataset(output_path: str, num_samples: int = 50):
    """生成示例评测数据集"""
    samples = []
    
    # 示例数据
    templates = [
        {
            "query": "需求评审结论",
            "topic": "需求评审",
            "meeting_type": "产品周会",
        },
        {
            "query": "技术方案决策",
            "topic": "技术方案",
            "meeting_type": "技术评审",
        },
        {
            "query": "遗留问题处理",
            "topic": "遗留问题",
            "meeting_type": "项目周会",
        },
    ]
    
    for i in range(num_samples):
        template = templates[i % len(templates)]
        samples.append({
            "query": f"{template['query']} {i+1}",
            "topic": template["topic"],
            "meeting_type": template["meeting_type"],
            "relevant_ids": [f"minutes_{i*3:03d}", f"minutes_{i*3+1:03d}"],
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    
    print(f"Sample dataset created: {output_path}")


if __name__ == "__main__":
    # 生成示例数据集
    create_sample_dataset("tests/evaluation/retrieval_dataset.json")
