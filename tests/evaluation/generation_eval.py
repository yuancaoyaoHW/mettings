"""
生成质量评测

评估指标：
- ROUGE：与参考纪要的文本重叠度
- BLEU：n-gram 精确度
- 结构化字段完整率
- 事实一致性（需人工或模型判断）
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from smart_minutes import SmartMinutesService
from smart_minutes.schemas import MinutesRequest, MinutesResponse

logger = logging.getLogger(__name__)


@dataclass
class GenerationExample:
    """生成评测样例"""
    request: MinutesRequest  # 输入请求
    reference_minutes: str  # 参考纪要（人工撰写）
    reference_structure: Dict  # 参考结构


@dataclass
class GenerationMetrics:
    """生成质量指标"""
    rouge_1: float = 0.0
    rouge_2: float = 0.0
    rouge_l: float = 0.0
    bleu: float = 0.0
    structure_completeness: float = 0.0  # 结构完整率
    field_accuracy: float = 0.0  # 字段准确率
    total_samples: int = 0


class GenerationEvaluator:
    """
    生成质量评测器
    
    对比生成的纪要与人工撰写的参考纪要
    """
    
    def __init__(self, service: SmartMinutesService):
        self.service = service
        self.examples: List[GenerationExample] = []
    
    def load_dataset(self, dataset_path: str) -> int:
        """
        加载评测数据集
        
        数据集格式（JSON）：
        [
          {
            "request": { ... MinutesRequest ... },
            "reference_minutes": "人工撰写的纪要正文",
            "reference_structure": {
              "meeting_info": { ... },
              "topics": [ ... ],
              "action_items": [ ... ]
            }
          }
        ]
        """
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.examples = []
            for item in data:
                self.examples.append(GenerationExample(
                    request=MinutesRequest(**item.get("request", {})),
                    reference_minutes=item.get("reference_minutes", ""),
                    reference_structure=item.get("reference_structure", {})
                ))
            
            logger.info(f"Loaded {len(self.examples)} generation examples")
            return len(self.examples)
            
        except Exception as e:
            logger.error(f"Failed to load dataset: {e}")
            return 0
    
    def evaluate(self) -> GenerationMetrics:
        """
        执行评测
        """
        if not self.examples:
            logger.warning("No evaluation examples loaded")
            return GenerationMetrics()
        
        metrics = GenerationMetrics(total_samples=len(self.examples))
        
        rouge_1_sum = 0.0
        rouge_2_sum = 0.0
        rouge_l_sum = 0.0
        bleu_sum = 0.0
        structure_sum = 0.0
        
        for example in self.examples:
            # 生成纪要
            try:
                response = self.service.run(example.request)
                generated = response.minutes_content
                
                # 计算文本相似度
                rouge_1_sum += self._calculate_rouge_n(
                    generated, example.reference_minutes, 1
                )
                rouge_2_sum += self._calculate_rouge_n(
                    generated, example.reference_minutes, 2
                )
                rouge_l_sum += self._calculate_rouge_l(
                    generated, example.reference_minutes
                )
                bleu_sum += self._calculate_bleu(
                    generated, example.reference_minutes
                )
                
                # 计算结构完整率
                structure_sum += self._calculate_structure_completeness(
                    response.structured_output,
                    example.reference_structure
                )
                
            except Exception as e:
                logger.error(f"Evaluation failed for example: {e}")
                continue
        
        n = len(self.examples)
        metrics.rouge_1 = rouge_1_sum / n
        metrics.rouge_2 = rouge_2_sum / n
        metrics.rouge_l = rouge_l_sum / n
        metrics.bleu = bleu_sum / n
        metrics.structure_completeness = structure_sum / n
        
        return metrics
    
    def _calculate_rouge_n(
        self,
        generated: str,
        reference: str,
        n: int
    ) -> float:
        """
        计算 ROUGE-N
        
        ROUGE-N = 共同 n-gram 数 / 参考 n-gram 数
        """
        gen_tokens = self._tokenize(generated)
        ref_tokens = self._tokenize(reference)
        
        gen_ngrams = self._get_ngrams(gen_tokens, n)
        ref_ngrams = self._get_ngrams(ref_tokens, n)
        
        if not ref_ngrams:
            return 0.0
        
        overlap = len(gen_ngrams & ref_ngrams)
        return overlap / len(ref_ngrams)
    
    def _calculate_rouge_l(
        self,
        generated: str,
        reference: str
    ) -> float:
        """
        计算 ROUGE-L（最长公共子序列）
        """
        gen_tokens = self._tokenize(generated)
        ref_tokens = self._tokenize(reference)
        
        lcs_length = self._lcs_length(gen_tokens, ref_tokens)
        
        if not ref_tokens:
            return 0.0
        
        return lcs_length / len(ref_tokens)
    
    def _calculate_bleu(
        self,
        generated: str,
        reference: str
    ) -> float:
        """
        计算 BLEU 分数（简化版）
        """
        gen_tokens = self._tokenize(generated)
        ref_tokens = self._tokenize(reference)
        
        # 计算 1-4 gram 的精确度
        precisions = []
        for n in range(1, 5):
            gen_ngrams = self._get_ngrams(gen_tokens, n)
            ref_ngrams = self._get_ngrams(ref_tokens, n)
            
            if not gen_ngrams:
                precisions.append(0.0)
            else:
                matches = len(gen_ngrams & ref_ngrams)
                precisions.append(matches / len(gen_ngrams))
        
        # 几何平均
        import math
        if all(p > 0 for p in precisions):
            geo_mean = math.exp(sum(math.log(p) for p in precisions) / 4)
        else:
            geo_mean = 0.0
        
        # 简短惩罚
        bp = 1.0
        if len(gen_tokens) < len(ref_tokens):
            bp = math.exp(1 - len(ref_tokens) / len(gen_tokens))
        
        return bp * geo_mean
    
    def _calculate_structure_completeness(
        self,
        generated_structure: Optional[object],
        reference_structure: Dict
    ) -> float:
        """
        计算结构完整率
        
        检查生成的结构化字段是否完整
        """
        if not generated_structure:
            return 0.0
        
        score = 0.0
        total_fields = 0
        
        # 检查 meeting_info
        if hasattr(generated_structure, 'meeting_info'):
            score += 1
            total_fields += 1
        
        # 检查 topics
        if hasattr(generated_structure, 'topics'):
            gen_topics = generated_structure.topics or []
            ref_topics = reference_structure.get('topics', [])
            
            if ref_topics:
                # 议题数量匹配度
                topic_score = min(len(gen_topics), len(ref_topics)) / len(ref_topics)
                score += topic_score
            total_fields += 1
        
        # 检查 action_items
        if hasattr(generated_structure, 'traceability'):
            score += 0.5
            total_fields += 1
        
        return score / total_fields if total_fields > 0 else 0.0
    
    def _tokenize(self, text: str) -> List[str]:
        """分词（简化版）"""
        # 移除标点，按空格/中文分词
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = text.lower().split()
        return tokens
    
    def _get_ngrams(self, tokens: List[str], n: int) -> set:
        """获取 n-gram 集合"""
        return set(tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1))
    
    def _lcs_length(self, seq1: List[str], seq2: List[str]) -> int:
        """计算最长公共子序列长度（动态规划）"""
        m, n = len(seq1), len(seq2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i-1] == seq2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        
        return dp[m][n]
    
    def generate_report(self, metrics: GenerationMetrics) -> str:
        """生成评测报告"""
        report = f"""
=== 生成质量评测报告 ===

评测样本数: {metrics.total_samples}

文本相似度指标:
  ROUGE-1:  {metrics.rouge_1:.3f}  (一元词重叠度)
  ROUGE-2:  {metrics.rouge_2:.3f}  (二元词重叠度)
  ROUGE-L:  {metrics.rouge_l:.3f}  (最长公共子序列)
  BLEU:     {metrics.bleu:.3f}     (n-gram精确度)

结构质量:
  结构完整率: {metrics.structure_completeness:.1%}

解读:
- ROUGE > 0.3: 可接受
- ROUGE > 0.5: 良好
- BLEU > 0.3: 流畅

===========================
"""
        return report


def create_sample_dataset(output_path: str, num_samples: int = 20):
    """生成示例评测数据集"""
    samples = []
    
    for i in range(num_samples):
        samples.append({
            "request": {
                "meeting_type": "产品周会",
                "meeting_name": f"产品周会第{i+1}期",
                "topics": ["需求评审", "进度同步"],
                "draft_text": f"讨论了需求A的功能设计和开发排期。结论：采用方案B，下周开始开发。",
            },
            "reference_minutes": f"""
# 产品周会第{i+1}期 会议纪要

## 会议信息
- 时间：2026-03-{i+1:02d}
- 参会人：张三、李四、王五

## 议题1：需求评审
- 讨论内容：需求A的功能设计
- 结论：采用方案B

## 议题2：进度同步
- 当前进度：50%
- 下阶段计划：开始开发

## 行动项
1. 【张三】完成技术设计 - 3月{i+5:02d}日
""",
            "reference_structure": {
                "meeting_info": {"meeting_type": "产品周会"},
                "topics": [
                    {"topic_name": "需求评审", "conclusions": ["采用方案B"]},
                    {"topic_name": "进度同步", "conclusions": ["当前进度50%"]},
                ],
                "action_items": [{"owner": "张三", "content": "完成技术设计"}]
            }
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    
    print(f"Sample dataset created: {output_path}")


if __name__ == "__main__":
    create_sample_dataset("tests/evaluation/generation_dataset.json")
