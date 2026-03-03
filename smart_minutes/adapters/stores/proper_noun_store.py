"""
专有名词存储（SQLAlchemy ORM）
专有名词仅提取不解释，按知识库维度存储，与 ProfessionalTerm 区分
"""
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)
Base = declarative_base()


class ProperNoun(Base):
    """专有名词表"""
    __tablename__ = 'proper_nouns'
    __table_args__ = {'comment': '专有名词表（仅提取不解释，按知识库存储）'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_name = Column(String(128), nullable=False, index=True, comment='知识库名')
    collection_name = Column(String(128), index=True, comment='Milvus 集合名（可与 kb_name 相同）')
    term = Column(String(256), nullable=False, comment='专有名词')
    source_doc = Column(String(256), comment='来源文档')
    source_id = Column(String(128), index=True, comment='来源 ID（如 meeting_id）')
    created_at = Column(DateTime, default=datetime.utcnow)


class ProperNounStore:
    """专有名词存储"""

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
        Base.metadata.create_all(self.engine)
        logger.info(f"Proper noun store initialized: {host}:{port}/{database}")

    def _get_session(self):
        return self.Session()

    def add_proper_nouns(
        self,
        kb_name: str,
        terms: List[str],
        *,
        collection_name: Optional[str] = None,
        source_doc: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> int:
        """
        批量添加专有名词，去重后写入。

        Returns:
            新增数量
        """
        if not terms:
            return 0
        session = self._get_session()
        try:
            coll = collection_name or kb_name
            seen = set()
            added = 0
            for term in terms:
                t = (term or "").strip()
                if not t or t in seen:
                    continue
                seen.add(t)
                existing = session.query(ProperNoun).filter(
                    ProperNoun.kb_name == kb_name,
                    ProperNoun.term == t,
                ).first()
                if not existing:
                    session.add(ProperNoun(
                        kb_name=kb_name,
                        collection_name=coll,
                        term=t,
                        source_doc=source_doc,
                        source_id=source_id,
                    ))
                    added += 1
            session.commit()
            return added
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add proper nouns: {e}")
            raise
        finally:
            session.close()

    def list_by_kb(
        self,
        kb_name: str,
        *,
        collection_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict:
        """
        按知识库查询专有名词列表，支持分页。

        Returns:
            {"items": [...], "total": int, "page": int, "page_size": int}
        """
        session = self._get_session()
        try:
            q = session.query(ProperNoun).filter(ProperNoun.kb_name == kb_name)
            if collection_name:
                q = q.filter(ProperNoun.collection_name == collection_name)
            total = q.count()
            offset = (page - 1) * page_size
            rows = q.order_by(ProperNoun.term).offset(offset).limit(page_size).all()
            items = [
                {
                    "id": r.id,
                    "term": r.term,
                    "source_doc": r.source_doc,
                    "source_id": r.source_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        except Exception as e:
            logger.error(f"Failed to list proper nouns: {e}")
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        finally:
            session.close()

    def close(self):
        if self.engine:
            self.engine.dispose()
            logger.info("Proper noun store connection closed")


def create_proper_noun_store_from_env() -> Optional[ProperNounStore]:
    """从环境变量创建专有名词存储"""
    db_uri = os.getenv("MAPPING_DB_URI", "")
    if db_uri:
        try:
            parsed = urlparse(db_uri)
            return ProperNounStore(
                host=parsed.hostname or "localhost",
                port=parsed.port or 3306,
                user=parsed.username or "",
                password=parsed.password or "",
                database=parsed.path.lstrip("/") or "smart_minutes",
            )
        except Exception as e:
            logger.error(f"Failed to parse DB URI: {e}")
            return None

    host = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", "3306"))
    user = os.getenv("MYSQL_USER") or os.getenv("DB_USER", "")
    password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "smart_minutes")

    if not user:
        logger.warning("MySQL config not found, proper noun store will not work")
        return None

    return ProperNounStore(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
