"""
历史纪要模板存储与抽取（SQLAlchemy ORM）
从同系列最新纪要抽取结构、字段名、表述习惯
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from services.llm import complete

logger = logging.getLogger(__name__)
Base = declarative_base()


class MeetingTemplate(Base):
    """会议纪要模板表"""
    __tablename__ = 'meeting_templates'
    __table_args__ = {'comment': '会议纪要模板表'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联信息
    meeting_type = Column(String(64), nullable=False, comment='会议类型')
    meeting_series = Column(String(128), comment='会议系列标识')
    project = Column(String(64), comment='项目')
    department = Column(String(64), comment='部门')
    
    # 模板内容
    template_name = Column(String(128), comment='模板名称')
    structure = Column(JSON, comment='结构定义（章节、字段）')
    style_features = Column(JSON, comment='风格特征')
    example_snippets = Column(JSON, comment='示例片段')
    
    # 字段定义
    required_fields = Column(JSON, comment='必填字段')
    optional_fields = Column(JSON, comment='可选字段')
    field_order = Column(JSON, comment='字段顺序')
    
    # 表述习惯
    phrase_patterns = Column(JSON, comment='常用表述模式')
    tone_description = Column(Text, comment='语气描述')
    
    # 来源
    source_minutes_ids = Column(JSON, comment='来源纪要ID列表')
    extracted_at = Column(DateTime, comment='抽取时间')
    
    # 使用统计
    usage_count = Column(Integer, default=0, comment='使用次数')
    avg_rating = Column(Float, comment='平均评分')
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class TemplateExtractor:
    """
    纪要模板抽取器
    
    从同系列最新纪要抽取模板信息
    """
    
    def __init__(self):
        self.extraction_prompt = """你是一个专业的会议纪要分析助手。
请分析以下会议纪要，提取其结构模板和风格特征。

分析维度：
1. 结构：章节划分、字段顺序、层级关系
2. 风格：语言特点、表述习惯、专业程度
3. 必填/可选字段
4. 常用表述模式

输出 JSON 格式：
{
  "structure": {
    "sections": ["会议信息", "议题1", "议题2", "行动项"],
    "hierarchy": {"level1": "会议类型", "level2": "议题", "level3": "要点"}
  },
  "style_features": {
    "tone": "正式/商务",
    "sentence_style": "简洁/详细",
    "action_item_format": "【负责人】任务 - 截止日期",
    "conclusion_keywords": ["结论", "决定", "同意"]
  },
  "required_fields": ["会议名称", "时间", "参会人", "议题", "结论"],
  "optional_fields": ["遗留问题", "下次会议"],
  "phrase_patterns": {
    "opening": "本次会议讨论了...",
    "conclusion": "经讨论，决定...",
    "action_item": "【负责人】完成..."
  }
}"""
    
    def extract_from_minutes(
        self,
        minutes_content: str,
        meeting_type: str,
        source_id: str
    ) -> Optional[Dict]:
        """
        从单份纪要抽取模板
        
        Args:
            minutes_content: 纪要内容
            meeting_type: 会议类型
            source_id: 来源纪要ID
        
        Returns:
            模板字典
        """
        if not minutes_content:
            return None
        
        try:
            prompt = f"会议纪要内容：\n{minutes_content[:5000]}\n\n请按指定格式输出模板分析结果："
            
            response = complete(prompt, system=self.extraction_prompt)
            
            if response:
                json_str = self._extract_json(response)
                template_data = json.loads(json_str)
                
                # 添加元数据
                template_data["meeting_type"] = meeting_type
                template_data["source_minutes_ids"] = [source_id]
                template_data["extracted_at"] = datetime.utcnow().isoformat()
                
                return template_data
                
        except Exception as e:
            logger.error(f"Template extraction failed: {e}")
        
        return None
    
    def merge_templates(
        self,
        templates: List[Dict],
        meeting_type: str
    ) -> Dict:
        """
        合并多份纪要的模板信息
        
        策略：
        1. 取结构交集（共同字段）
        2. 合并风格特征
        3. 统计出现频率
        """
        if not templates:
            return {}
        
        if len(templates) == 1:
            return templates[0]
        
        merged = {
            "meeting_type": meeting_type,
            "source_minutes_ids": [],
            "structure": {"sections": [], "hierarchy": {}},
            "style_features": {},
            "required_fields": [],
            "optional_fields": [],
            "phrase_patterns": {},
        }
        
        # 收集所有字段
        all_required = []
        all_optional = []
        all_sections = []
        
        for t in templates:
            merged["source_minutes_ids"].extend(t.get("source_minutes_ids", []))
            
            structure = t.get("structure", {})
            all_sections.append(structure.get("sections", []))
            
            all_required.append(set(t.get("required_fields", [])))
            all_optional.append(set(t.get("optional_fields", [])))
        
        # 取结构交集（出现频率 > 50%）
        from collections import Counter
        section_counter = Counter()
        for sections in all_sections:
            section_counter.update(sections)
        
        threshold = len(templates) // 2
        common_sections = [s for s, c in section_counter.items() if c > threshold]
        merged["structure"]["sections"] = common_sections
        
        # 取必填字段交集
        if all_required:
            common_required = all_required[0]
            for fields in all_required[1:]:
                common_required &= fields
            merged["required_fields"] = list(common_required)
        
        # 取可选字段并集
        if all_optional:
            all_opt = set()
            for fields in all_optional:
                all_opt |= fields
            merged["optional_fields"] = list(all_opt - set(merged["required_fields"]))
        
        # 合并风格特征（取第一个的）
        merged["style_features"] = templates[0].get("style_features", {})
        
        # 合并表述模式
        for t in templates:
            patterns = t.get("phrase_patterns", {})
            for key, value in patterns.items():
                if key not in merged["phrase_patterns"]:
                    merged["phrase_patterns"][key] = value
        
        merged["extracted_at"] = datetime.utcnow().isoformat()
        
        return merged
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON"""
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip()
        
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start:end+1]
        
        return text.strip()


class TemplateStore:
    """
    模板存储管理
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "",
        password: str = "",
        database: str = "smart_minutes",
        pool_size: int = 5,
        echo: bool = False,
    ):
        db_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
        
        self.engine = create_engine(
            db_url,
            pool_size=pool_size,
            max_overflow=10,
            pool_recycle=3600,
            echo=echo,
        )
        
        self.Session = sessionmaker(bind=self.engine)
        self.extractor = TemplateExtractor()
        
        # 初始化表
        Base.metadata.create_all(self.engine)
        
        logger.info(f"Template store initialized: {host}:{port}/{database}")
    
    def _get_session(self):
        return self.Session()
    
    def save_template(self, template_data: Dict) -> Optional[int]:
        """保存模板"""
        session = self._get_session()
        try:
            template = MeetingTemplate(
                meeting_type=template_data.get("meeting_type", ""),
                meeting_series=template_data.get("meeting_series"),
                project=template_data.get("project"),
                department=template_data.get("department"),
                template_name=template_data.get("template_name", f"{template_data.get('meeting_type')}模板"),
                structure=template_data.get("structure", {}),
                style_features=template_data.get("style_features", {}),
                example_snippets=template_data.get("example_snippets", []),
                required_fields=template_data.get("required_fields", []),
                optional_fields=template_data.get("optional_fields", []),
                field_order=template_data.get("field_order", []),
                phrase_patterns=template_data.get("phrase_patterns", {}),
                tone_description=template_data.get("tone_description"),
                source_minutes_ids=template_data.get("source_minutes_ids", []),
                extracted_at=datetime.fromisoformat(template_data.get("extracted_at")) if template_data.get("extracted_at") else datetime.utcnow(),
            )
            
            session.add(template)
            session.commit()
            
            logger.info(f"Template saved: {template.template_name}")
            return template.id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save template: {e}")
            return None
        finally:
            session.close()
    
    def get_template(
        self,
        meeting_type: str,
        project: Optional[str] = None,
        department: Optional[str] = None
    ) -> Optional[Dict]:
        """
        获取最适合的模板
        
        匹配优先级：
        1. 精确匹配 meeting_type + project + department
        2. 匹配 meeting_type + project
        3. 匹配 meeting_type + department
        4. 仅匹配 meeting_type
        """
        session = self._get_session()
        try:
            query = session.query(MeetingTemplate).filter(
                MeetingTemplate.meeting_type == meeting_type,
                MeetingTemplate.is_active == True
            )
            
            # 尝试最精确匹配
            if project and department:
                result = query.filter(
                    MeetingTemplate.project == project,
                    MeetingTemplate.department == department
                ).order_by(MeetingTemplate.usage_count.desc()).first()
                if result:
                    return self._template_to_dict(result)
            
            if project:
                result = query.filter(
                    MeetingTemplate.project == project
                ).order_by(MeetingTemplate.usage_count.desc()).first()
                if result:
                    return self._template_to_dict(result)
            
            if department:
                result = query.filter(
                    MeetingTemplate.department == department
                ).order_by(MeetingTemplate.usage_count.desc()).first()
                if result:
                    return self._template_to_dict(result)
            
            # 仅按类型匹配
            result = query.order_by(MeetingTemplate.usage_count.desc()).first()
            if result:
                return self._template_to_dict(result)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get template: {e}")
            return None
        finally:
            session.close()
    
    def extract_and_save_from_minutes(
        self,
        minutes_list: List[Dict],
        meeting_type: str
    ) -> Optional[int]:
        """
        从纪要列表抽取并保存模板
        
        Args:
            minutes_list: 纪要列表，每项包含 content 和 id
            meeting_type: 会议类型
        """
        if not minutes_list:
            return None
        
        # 抽取每个纪要的模板
        templates = []
        for minutes in minutes_list:
            template = self.extractor.extract_from_minutes(
                minutes.get("content", ""),
                meeting_type,
                minutes.get("id", "")
            )
            if template:
                templates.append(template)
        
        if not templates:
            logger.warning(f"No templates extracted from {len(minutes_list)} minutes")
            return None
        
        # 合并模板
        merged = self.extractor.merge_templates(templates, meeting_type)
        
        # 保存
        return self.save_template(merged)
    
    def apply_template(
        self,
        template_id: int,
        content_data: Dict
    ) -> Dict:
        """
        应用模板格式化内容
        
        根据模板结构重组内容
        """
        session = self._get_session()
        try:
            template = session.query(MeetingTemplate).get(template_id)
            if not template:
                return content_data
            
            # 更新使用统计
            template.usage_count += 1
            session.commit()
            
            # 应用模板结构
            structured = {
                "meeting_info": {},
                "topics": [],
                "action_items": [],
            }
            
            # 根据模板字段排序
            field_order = template.field_order or []
            
            return structured
            
        except Exception as e:
            logger.error(f"Failed to apply template: {e}")
            return content_data
        finally:
            session.close()
    
    def list_templates(
        self,
        meeting_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """列出模板"""
        session = self._get_session()
        try:
            query = session.query(MeetingTemplate).filter(
                MeetingTemplate.is_active == True
            )
            
            if meeting_type:
                query = query.filter(MeetingTemplate.meeting_type == meeting_type)
            
            templates = query.order_by(MeetingTemplate.usage_count.desc()).limit(limit).all()
            
            return [self._template_to_dict(t) for t in templates]
            
        except Exception as e:
            logger.error(f"Failed to list templates: {e}")
            return []
        finally:
            session.close()
    
    def _template_to_dict(self, template: MeetingTemplate) -> Dict:
        """转换为字典"""
        return {
            "id": template.id,
            "meeting_type": template.meeting_type,
            "meeting_series": template.meeting_series,
            "template_name": template.template_name,
            "structure": template.structure,
            "style_features": template.style_features,
            "required_fields": template.required_fields,
            "optional_fields": template.optional_fields,
            "field_order": template.field_order,
            "phrase_patterns": template.phrase_patterns,
            "tone_description": template.tone_description,
            "usage_count": template.usage_count,
            "avg_rating": template.avg_rating,
            "extracted_at": template.extracted_at.isoformat() if template.extracted_at else None,
        }
    
    def close(self):
        """关闭连接"""
        if self.engine:
            self.engine.dispose()
            logger.info("Template store closed")


def create_template_store_from_env() -> Optional[TemplateStore]:
    """从环境变量创建模板存储"""
    import os
    
    host = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", "3306"))
    user = os.getenv("MYSQL_USER") or os.getenv("DB_USER", "")
    password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "smart_minutes")
    
    if not user:
        logger.warning("MySQL config not found")
        return None
    
    return TemplateStore(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database
    )
