"""
口水稿工具：语义段落切分与议题对齐

使用 Qwen3-30B-A3B 进行高质量语义切分，支持：
- 语义段落识别
- 议题边界检测
- 不确定性标记
- 一段多议题支持
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from services.llm import complete

logger = logging.getLogger(__name__)


@dataclass
class SegmentConfidence:
    """段落切分置信度"""
    boundary_confidence: float = 0.0  # 边界置信度
    topic_alignment: float = 0.0  # 议题对齐度
    overall: float = 0.0  # 综合置信度
    
    def is_low_confidence(self, threshold: float = 0.6) -> bool:
        """是否低置信度"""
        return self.overall < threshold


@dataclass
class DraftSegment:
    """口水稿段落"""
    text: str
    topic: str
    start_pos: int
    end_pos: int
    confidence: SegmentConfidence = field(default_factory=SegmentConfidence)
    alternative_topics: List[str] = field(default_factory=list)  # 候选议题
    is_ambiguous: bool = False  # 是否模糊
    speakers: List[str] = field(default_factory=list)  # 发言人


@dataclass
class SegmentationResult:
    """切分结果"""
    segments: List[DraftSegment] = field(default_factory=list)
    ambiguous_segments: List[DraftSegment] = field(default_factory=list)  # 模糊段落
    unassigned_text: str = ""  # 未分配文本
    total_length: int = 0


class SemanticDraftSegmenter:
    """
    语义口水稿切分器
    
    使用 LLM 理解语义，智能切分段落并映射到议题
    """
    
    def __init__(
        self,
        confidence_threshold: float = 0.6,
        max_segment_length: int = 2000,
        min_segment_length: int = 50,
    ):
        self.confidence_threshold = confidence_threshold
        self.max_segment_length = max_segment_length
        self.min_segment_length = min_segment_length
    
    def segment_by_topics(
        self,
        draft_text: str,
        topic_names: List[str],
        meeting_context: str = ""
    ) -> SegmentationResult:
        """
        按议题切分口水稿
        
        Args:
            draft_text: 口水稿全文
            topic_names: 议题列表
            meeting_context: 会议上下文（类型、名称等）
        
        Returns:
            SegmentationResult 包含切分段落和不确定性标记
        """
        if not draft_text or not topic_names:
            return SegmentationResult()
        
        # 1. 使用 LLM 进行语义切分
        segments = self._semantic_segmentation(draft_text, topic_names, meeting_context)
        
        # 2. 后处理：合并过短段落、处理重叠
        segments = self._post_process_segments(segments)
        
        # 3. 计算置信度并标记模糊段落
        result = self._calculate_confidence(segments, draft_text)
        
        result.total_length = len(draft_text)
        return result
    
    def _semantic_segmentation(
        self,
        draft_text: str,
        topic_names: List[str],
        meeting_context: str
    ) -> List[DraftSegment]:
        """
        使用 LLM 进行语义切分
        """
        # 构建提示词
        system_prompt = """你是一个专业的会议纪要分析助手。你的任务是将会议转写文本（口水稿）按议题切分。

要求：
1. 识别文本中的自然段落边界（话题转换、发言人变更等）
2. 将每个段落归类到给定的议题之一
3. 如果一段内容涉及多个议题，列出所有相关议题
4. 评估每个段落边界的置信度（0-1）
5. 标记置信度低的段落（可能需要人工校对）

输出格式必须是 JSON：
{
  "segments": [
    {
      "text": "段落文本（保持原样）",
      "topic": "主要议题名",
      "start_pos": 起始位置,
      "end_pos": 结束位置,
      "alternative_topics": ["备选议题1", "备选议题2"],
      "speakers": ["发言人1", "发言人2"],
      "confidence": 0.85
    }
  ],
  "unassigned": "无法归类的文本（如有）"
}"""
        
        user_prompt = f"""请将以下会议口水稿按议题切分。

会议信息：{meeting_context}

议题列表：
{chr(10).join([f"- {t}" for t in topic_names])}

口水稿内容：
{draft_text[:8000]}  # 限制长度避免超出上下文

请按 JSON 格式输出切分结果。"""
        
        try:
            response = complete(user_prompt, system=system_prompt)
            
            # 解析 JSON
            if response:
                # 提取 JSON 部分
                json_str = self._extract_json(response)
                if json_str:
                    data = json.loads(json_str)
                    return self._parse_segments(data, draft_text)
            
        except Exception as e:
            logger.error(f"LLM segmentation failed: {e}")
        
        # 回退到简单切分
        return self._fallback_segmentation(draft_text, topic_names)
    
    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取 JSON"""
        # 尝试找到 JSON 代码块
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip()
        
        # 尝试找到 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start:end+1]
        
        return text.strip()
    
    def _parse_segments(
        self,
        data: dict,
        full_text: str
    ) -> List[DraftSegment]:
        """解析 LLM 返回的切分结果"""
        segments = []
        
        for seg_data in data.get("segments", []):
            segment = DraftSegment(
                text=seg_data.get("text", ""),
                topic=seg_data.get("topic", "未分类"),
                start_pos=seg_data.get("start_pos", 0),
                end_pos=seg_data.get("end_pos", 0),
                confidence=SegmentConfidence(
                    overall=seg_data.get("confidence", 0.5)
                ),
                alternative_topics=seg_data.get("alternative_topics", []),
                speakers=seg_data.get("speakers", []),
            )
            
            # 验证位置
            if segment.text and segment.start_pos >= 0:
                # 如果位置不匹配，尝试在原文中查找
                if full_text[segment.start_pos:segment.end_pos] != segment.text:
                    idx = full_text.find(segment.text)
                    if idx >= 0:
                        segment.start_pos = idx
                        segment.end_pos = idx + len(segment.text)
            
            segments.append(segment)
        
        return segments
    
    def _fallback_segmentation(
        self,
        draft_text: str,
        topic_names: List[str]
    ) -> List[DraftSegment]:
        """
        回退切分策略：基于关键词的简单切分
        """
        import re
        
        segments = []
        
        # 先按句子切分
        sentences = re.split(r'(?<=[。！？\n])', draft_text)
        
        current_segment = ""
        current_topic = topic_names[0] if topic_names else "未分类"
        start_pos = 0
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # 检测议题关键词
            detected_topic = self._detect_topic_by_keywords(sentence, topic_names)
            
            if detected_topic and detected_topic != current_topic:
                # 保存当前段落
                if len(current_segment) >= self.min_segment_length:
                    segments.append(DraftSegment(
                        text=current_segment.strip(),
                        topic=current_topic,
                        start_pos=start_pos,
                        end_pos=start_pos + len(current_segment),
                        confidence=SegmentConfidence(overall=0.3)  # 低置信度
                    ))
                
                # 开始新段落
                current_segment = sentence
                current_topic = detected_topic
                start_pos = draft_text.find(sentence, start_pos)
            else:
                current_segment += sentence
        
        # 保存最后一段
        if len(current_segment) >= self.min_segment_length:
            segments.append(DraftSegment(
                text=current_segment.strip(),
                topic=current_topic,
                start_pos=start_pos,
                end_pos=start_pos + len(current_segment),
                confidence=SegmentConfidence(overall=0.3)
            ))
        
        return segments
    
    def _detect_topic_by_keywords(
        self,
        text: str,
        topic_names: List[str]
    ) -> Optional[str]:
        """基于关键词检测议题"""
        text_lower = text.lower()
        
        for topic in topic_names:
            # 检查议题名是否出现在文本中
            if topic.lower() in text_lower:
                return topic
            # 检查前两个字
            if len(topic) >= 2 and topic[:2] in text:
                return topic
        
        return None
    
    def _post_process_segments(
        self,
        segments: List[DraftSegment]
    ) -> List[DraftSegment]:
        """后处理：合并短段落、处理重叠"""
        if not segments:
            return segments
        
        # 排序
        segments.sort(key=lambda x: x.start_pos)
        
        # 合并过短的段落
        merged = []
        i = 0
        while i < len(segments):
            current = segments[i]
            
            # 尝试合并后续短段落
            while (i + 1 < len(segments) and 
                   len(current.text) < self.min_segment_length and
                   segments[i + 1].topic == current.topic):
                next_seg = segments[i + 1]
                current.text += " " + next_seg.text
                current.end_pos = next_seg.end_pos
                i += 1
            
            merged.append(current)
            i += 1
        
        return merged
    
    def _calculate_confidence(
        self,
        segments: List[DraftSegment],
        full_text: str
    ) -> SegmentationResult:
        """计算置信度并标记模糊段落"""
        result = SegmentationResult()
        
        covered_ranges = []
        
        for segment in segments:
            conf = segment.confidence
            
            # 基于文本特征调整置信度
            if len(segment.text) < self.min_segment_length:
                conf.overall *= 0.8
            
            if len(segment.alternative_topics) > 1:
                conf.overall *= 0.9  # 多议题稍微降低置信度
                segment.is_ambiguous = True
            
            # 检查与其他段落是否有重叠
            for start, end in covered_ranges:
                if not (segment.end_pos <= start or segment.start_pos >= end):
                    conf.overall *= 0.7  # 重叠降低置信度
                    segment.is_ambiguous = True
                    break
            
            covered_ranges.append((segment.start_pos, segment.end_pos))
            
            # 分类
            if conf.is_low_confidence(self.confidence_threshold):
                result.ambiguous_segments.append(segment)
            else:
                result.segments.append(segment)
        
        # 计算覆盖率
        covered_length = sum(end - start for start, end in covered_ranges)
        if covered_length < len(full_text):
            result.unassigned_text = full_text[covered_length:]
        
        return result
    
    def get_draft_segments_by_topics(
        self,
        draft_text: str,
        topic_names: List[str]
    ) -> List[Dict]:
        """
        兼容旧接口：返回简单字典格式
        """
        result = self.segment_by_topics(draft_text, topic_names)
        
        output = []
        for segment in result.segments:
            output.append({
                "topic": segment.topic,
                "page_content": segment.text,
                "start_pos": segment.start_pos,
                "end_pos": segment.end_pos,
                "confidence": segment.confidence.overall,
                "is_ambiguous": segment.is_ambiguous,
                "alternative_topics": segment.alternative_topics,
            })
        
        # 添加模糊标记
        if result.ambiguous_segments:
            output.append({
                "type": "ambiguity_warning",
                "ambiguous_segments": [
                    {
                        "topic": s.topic,
                        "text_preview": s.text[:100] + "...",
                        "confidence": s.confidence.overall,
                        "alternative_topics": s.alternative_topics,
                    }
                    for s in result.ambiguous_segments
                ],
                "message": f"发现 {len(result.ambiguous_segments)} 个模糊段落，建议人工校对"
            })
        
        return output


# 便捷函数
def get_draft_segments_by_topics(
    draft_text: str,
    topic_names: List[str]
) -> List[Dict]:
    """
    按议题名对口水稿做语义分割
    
    新的实现使用 LLM 进行语义切分，支持不确定性标记
    """
    segmenter = SemanticDraftSegmenter()
    return segmenter.get_draft_segments_by_topics(draft_text, topic_names)


def segment_transcript_with_confidence(
    draft_text: str,
    topic_names: List[str],
    meeting_context: str = ""
) -> SegmentationResult:
    """
    高级接口：返回完整的切分结果（含置信度）
    """
    segmenter = SemanticDraftSegmenter()
    return segmenter.segment_by_topics(draft_text, topic_names, meeting_context)
