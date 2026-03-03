"""
MySQL 实现的映射存储（SQLAlchemy ORM 版本）
支持口头称呼→正式人名、专业术语映射的持久化
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, ForeignKey, 
    Integer, String, Text, create_engine, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

from smart_minutes.contracts import IMappingStore

logger = logging.getLogger(__name__)
Base = declarative_base()


# ========== ORM 模型定义 ==========

class OralNameMapping(Base):
    """口头称呼映射表"""
    __tablename__ = 'oral_name_mapping'
    __table_args__ = (
        UniqueConstraint('oral_name', 'is_active', name='uk_oral_name_active'),
        {'comment': '口头称呼映射表'}
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    oral_name = Column(String(128), nullable=False, comment='口头称呼')
    formal_name = Column(String(128), nullable=False, comment='正式人名')
    employee_id = Column(String(64), comment='员工ID')
    department = Column(String(64), comment='部门')
    confidence = Column(Float, default=1.0, comment='置信度')
    source = Column(String(32), comment='来源：manual/import/system')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(64), comment='创建人')
    is_active = Column(Boolean, default=True, comment='是否启用')


class ProfessionalTerm(Base):
    """专业术语表"""
    __tablename__ = 'professional_terms'
    __table_args__ = {'comment': '专业术语表'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    term = Column(String(128), nullable=False, unique=True, comment='标准术语')
    aliases = Column(JSON, comment='别名列表')
    abbreviation = Column(String(64), comment='缩写')
    category = Column(String(64), comment='分类')
    description = Column(Text, comment='解释')
    meeting_types = Column(JSON, comment='适用的会议类型')
    source_doc = Column(String(256), comment='来源文档')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # 关联
    meeting_type_links = relationship("MeetingTypeTerm", back_populates="term")


class MeetingTypeTerm(Base):
    """会议类型术语关联表"""
    __tablename__ = 'meeting_type_terms'
    __table_args__ = (
        UniqueConstraint('meeting_type', 'term_id', name='uk_meeting_term'),
        {'comment': '会议类型术语关联表'}
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_type = Column(String(64), nullable=False, comment='会议类型')
    term_id = Column(Integer, ForeignKey('professional_terms.id'), nullable=False)
    relevance_score = Column(Float, default=1.0, comment='关联度')
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联
    term = relationship("ProfessionalTerm", back_populates="meeting_type_links")


# ========== 存储实现 ==========

class MappingStoreMySQL(IMappingStore):
    """MySQL ORM 实现的 IMappingStore"""
    
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
        # 创建数据库连接
        db_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
        
        self.engine = create_engine(
            db_url,
            pool_size=pool_size,
            max_overflow=10,
            pool_recycle=3600,
            echo=echo,
        )
        
        self.Session = sessionmaker(bind=self.engine)
        
        # 初始化表结构
        self._init_db()
        
        logger.info(f"MySQL mapping store initialized: {host}:{port}/{database}")
    
    def _init_db(self):
        """初始化数据库表"""
        try:
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created/verified")
        except Exception as e:
            logger.error(f"Failed to init database: {e}")
            raise
    
    def _get_session(self):
        """获取数据库会话"""
        return self.Session()
    
    # ========== IMappingStore 接口实现 ==========
    
    def resolve_oral_to_formal(self, oral_name: str) -> Optional[str]:
        """
        口头称呼 → 正式人名（取第一个/最高置信度）

        策略：
        1. 精确匹配
        2. 模糊匹配（去掉常用前缀如"小"、"老"）
        3. 返回置信度最高的结果
        """
        candidates = self.resolve_oral_to_formal_candidates(oral_name)
        return candidates[0] if candidates else None

    def resolve_oral_to_formal_candidates(self, oral_name: str) -> List[str]:
        """
        口头称呼 → 所有正式人名候选（is_active=True，按 confidence 排序）
        """
        if not oral_name:
            return []

        session = self._get_session()
        try:
            # 1. 精确匹配
            results = session.query(OralNameMapping).filter(
                OralNameMapping.oral_name == oral_name,
                OralNameMapping.is_active == True
            ).order_by(
                OralNameMapping.confidence.desc(),
                OralNameMapping.updated_at.desc()
            ).all()

            if results:
                return [r.formal_name for r in results]

            # 2. 模糊匹配
            variations = self._generate_name_variations(oral_name)
            if variations:
                results = session.query(OralNameMapping).filter(
                    OralNameMapping.oral_name.in_(variations),
                    OralNameMapping.is_active == True
                ).order_by(
                    OralNameMapping.confidence.desc()
                ).all()
                if results:
                    return [r.formal_name for r in results]

            return []

        except Exception as e:
            logger.error(f"Failed to resolve oral name: {e}")
            return []
        finally:
            session.close()
    
    def get_professional_terms(
        self,
        meeting_type: str,
        meeting_name: str = ""
    ) -> List[str]:
        """
        获取会议类型相关的专业术语
        
        Returns:
            术语列表，按关联度排序
        """
        session = self._get_session()
        try:
            # 查询会议类型关联的术语
            results = session.query(ProfessionalTerm).join(
                MeetingTypeTerm
            ).filter(
                MeetingTypeTerm.meeting_type == meeting_type,
                ProfessionalTerm.is_active == True
            ).order_by(
                MeetingTypeTerm.relevance_score.desc(),
                ProfessionalTerm.term
            ).all()
            
            terms = []
            for term in results:
                terms.append(term.term)
                # 也添加别名
                if term.aliases:
                    if isinstance(term.aliases, str):
                        try:
                            aliases = json.loads(term.aliases)
                            terms.extend(aliases)
                        except:
                            pass
                    elif isinstance(term.aliases, list):
                        terms.extend(term.aliases)
            
            # 去重保持顺序
            seen = set()
            unique_terms = []
            for t in terms:
                if t not in seen:
                    seen.add(t)
                    unique_terms.append(t)
            
            return unique_terms
            
        except Exception as e:
            logger.error(f"Failed to get professional terms: {e}")
            return []
        finally:
            session.close()
    
    # ========== 扩展功能 ==========
    
    def batch_resolve_oral_names(
        self,
        oral_names: List[str]
    ) -> Dict[str, Optional[str]]:
        """批量解析口头称呼"""
        results = {}
        for name in oral_names:
            results[name] = self.resolve_oral_to_formal(name)
        return results
    
    def add_or_update_oral_name_mapping(
        self,
        oral_name: str,
        formal_name: str,
        employee_id: str = "",
        department: str = "",
        confidence: float = 1.0,
        source: str = "manual",
        created_by: str = ""
    ) -> bool:
        """添加或更新单条口头称呼映射（API 可调用）。"""
        return self.add_oral_name_mapping(
            oral_name, formal_name, employee_id, department, confidence, source, created_by
        )

    def batch_add_or_update_oral_name_mappings(
        self,
        mappings: List[Dict],
    ) -> Dict[str, int]:
        """
        批量添加或更新口头称呼映射。

        Args:
            mappings: List[{ "oral_name", "formal_name", "employee_id"? }]

        Returns:
            {"success_count": int, "failed_count": int}
        """
        success_count = 0
        failed_count = 0
        for m in mappings:
            oral = m.get("oral_name") or ""
            formal = m.get("formal_name") or ""
            if not oral or not formal:
                failed_count += 1
                continue
            if self.add_oral_name_mapping(
                oral_name=oral,
                formal_name=formal,
                employee_id=m.get("employee_id", ""),
            ):
                success_count += 1
            else:
                failed_count += 1
        return {"success_count": success_count, "failed_count": failed_count}

    def add_oral_name_mapping(
        self,
        oral_name: str,
        formal_name: str,
        employee_id: str = "",
        department: str = "",
        confidence: float = 1.0,
        source: str = "manual",
        created_by: str = ""
    ) -> bool:
        """添加或更新口头称呼映射"""
        session = self._get_session()
        try:
            # 查找现有记录
            existing = session.query(OralNameMapping).filter(
                OralNameMapping.oral_name == oral_name
            ).first()
            
            if existing:
                # 更新
                existing.formal_name = formal_name
                existing.employee_id = employee_id
                existing.department = department
                existing.confidence = confidence
                existing.source = source
                existing.is_active = True
            else:
                # 新建
                mapping = OralNameMapping(
                    oral_name=oral_name,
                    formal_name=formal_name,
                    employee_id=employee_id,
                    department=department,
                    confidence=confidence,
                    source=source,
                    created_by=created_by,
                    is_active=True
                )
                session.add(mapping)
            
            session.commit()
            logger.info(f"Added/Updated mapping: {oral_name} -> {formal_name}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add mapping: {e}")
            return False
        finally:
            session.close()
    
    def add_professional_term(
        self,
        term: str,
        aliases: List[str] = None,
        abbreviation: str = "",
        category: str = "",
        description: str = "",
        meeting_types: List[str] = None
    ) -> bool:
        """添加或更新专业术语"""
        session = self._get_session()
        try:
            # 查找或创建术语
            prof_term = session.query(ProfessionalTerm).filter(
                ProfessionalTerm.term == term
            ).first()
            
            if prof_term:
                prof_term.aliases = aliases or []
                prof_term.abbreviation = abbreviation
                prof_term.category = category
                prof_term.description = description
                prof_term.meeting_types = meeting_types or []
                prof_term.is_active = True
            else:
                prof_term = ProfessionalTerm(
                    term=term,
                    aliases=aliases or [],
                    abbreviation=abbreviation,
                    category=category,
                    description=description,
                    meeting_types=meeting_types or [],
                    is_active=True
                )
                session.add(prof_term)
                session.flush()  # 获取 ID
            
            # 关联会议类型
            for mt in (meeting_types or []):
                link = session.query(MeetingTypeTerm).filter(
                    MeetingTypeTerm.meeting_type == mt,
                    MeetingTypeTerm.term_id == prof_term.id
                ).first()
                
                if not link:
                    link = MeetingTypeTerm(
                        meeting_type=mt,
                        term_id=prof_term.id
                    )
                    session.add(link)
            
            session.commit()
            logger.info(f"Added/Updated term: {term}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add term: {e}")
            return False
        finally:
            session.close()
    
    def delete_oral_name_mapping(self, oral_name: str, soft_delete: bool = True) -> bool:
        """删除口头称呼映射"""
        session = self._get_session()
        try:
            mapping = session.query(OralNameMapping).filter(
                OralNameMapping.oral_name == oral_name
            ).first()
            
            if mapping:
                if soft_delete:
                    mapping.is_active = False
                else:
                    session.delete(mapping)
                session.commit()
                logger.info(f"Deleted mapping: {oral_name}")
                return True
            return False
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete mapping: {e}")
            return False
        finally:
            session.close()
    
    def get_mapping_stats(self) -> Dict[str, int]:
        """获取映射统计信息"""
        session = self._get_session()
        try:
            oral_count = session.query(OralNameMapping).filter(
                OralNameMapping.is_active == True
            ).count()
            
            term_count = session.query(ProfessionalTerm).filter(
                ProfessionalTerm.is_active == True
            ).count()
            
            return {
                "oral_name_mappings": oral_count,
                "professional_terms": term_count
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
        finally:
            session.close()
    
    def search_oral_names(
        self,
        keyword: str,
        limit: int = 10
    ) -> List[Dict]:
        """搜索口头称呼映射"""
        session = self._get_session()
        try:
            results = session.query(OralNameMapping).filter(
                OralNameMapping.oral_name.contains(keyword),
                OralNameMapping.is_active == True
            ).limit(limit).all()
            
            return [
                {
                    "oral_name": r.oral_name,
                    "formal_name": r.formal_name,
                    "employee_id": r.employee_id,
                    "department": r.department,
                    "confidence": r.confidence,
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to search: {e}")
            return []
        finally:
            session.close()
    
    def _generate_name_variations(self, name: str) -> List[str]:
        """生成名称变体用于模糊匹配"""
        variations = []
        
        # 去掉常见前缀
        prefixes = ["小", "老", "大", "阿"]
        for prefix in prefixes:
            if name.startswith(prefix):
                variations.append(name[len(prefix):])
        
        # 添加完整名变体
        if len(name) >= 2:
            variations.append(name[1:])  # 去掉第一个字
            variations.append(name[:-1])  # 去掉最后一个字
        
        return list(set(variations))
    
    def close(self):
        """关闭连接"""
        if self.engine:
            self.engine.dispose()
            logger.info("MySQL connection closed")


def create_mapping_store_from_env() -> Optional[MappingStoreMySQL]:
    """从环境变量创建 MySQL 映射存储"""
    import os
    
    db_uri = os.getenv("MAPPING_DB_URI", "")
    if db_uri:
        # 解析 URI: mysql://user:pass@host:port/database
        try:
            from urllib.parse import urlparse
            parsed = urlparse(db_uri)
            return MappingStoreMySQL(
                host=parsed.hostname or "localhost",
                port=parsed.port or 3306,
                user=parsed.username or "",
                password=parsed.password or "",
                database=parsed.path.lstrip("/") or "smart_minutes"
            )
        except Exception as e:
            logger.error(f"Failed to parse DB URI: {e}")
            return None
    
    # 从独立环境变量构建（兼容 DB_* 命名）
    host = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", "3306"))
    user = os.getenv("MYSQL_USER") or os.getenv("DB_USER", "")
    password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "smart_minutes")
    
    if not user:
        logger.warning("MySQL config not found, mapping store will not work")
        return None
    
    return MappingStoreMySQL(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database
    )
