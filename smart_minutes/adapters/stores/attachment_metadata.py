"""
附件元数据管理（SQLAlchemy ORM）
管理附件的文件名、URL、类型等元数据，与 Milvus chunk 关联
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

logger = logging.getLogger(__name__)
Base = declarative_base()


class Attachment(Base):
    """附件元数据表"""
    __tablename__ = 'attachments'
    __table_args__ = {'comment': '附件元数据表'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String(128), unique=True, nullable=False, comment='文件唯一标识')
    file_name = Column(String(256), nullable=False, comment='文件名')
    file_type = Column(String(64), comment='文件类型：pdf/doc/xlsx等')
    file_size = Column(Integer, comment='文件大小（字节）')
    file_url = Column(String(512), comment='文件访问URL')
    storage_path = Column(String(512), comment='存储路径')
    
    # 会议关联
    meeting_id = Column(String(64), comment='关联会议ID')
    meeting_type = Column(String(64), comment='会议类型')
    meeting_name = Column(String(256), comment='会议名称')
    
    # 权限
    uploader = Column(String(128), comment='上传人')
    department = Column(String(64), comment='所属部门')
    permission_level = Column(String(32), default="internal", comment='权限级别：public/internal/confidential')
    allowed_users = Column(JSON, comment='允许访问的用户列表')
    
    # 版本控制
    version = Column(String(32), default="1.0", comment='版本号')
    version_notes = Column(Text, comment='版本说明')
    is_latest = Column(Boolean, default=True, comment='是否最新版本')
    parent_version = Column(String(32), comment='父版本号')
    
    # 内容摘要
    content_summary = Column(Text, comment='内容摘要')
    keywords = Column(JSON, comment='关键词')
    page_count = Column(Integer, comment='页数')
    
    # Milvus 关联
    milvus_collection = Column(String(128), comment='Milvus集合名')
    chunk_count = Column(Integer, default=0, comment='Chunk数量')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    uploaded_at = Column(DateTime, comment='实际上传时间')
    
    is_active = Column(Boolean, default=True)
    
    # 关联
    chunks = relationship("AttachmentChunk", back_populates="attachment", cascade="all, delete-orphan")


class AttachmentChunk(Base):
    """附件 Chunk 关联表"""
    __tablename__ = 'attachment_chunks'
    __table_args__ = {'comment': '附件Chunk关联表'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    attachment_id = Column(Integer, ForeignKey('attachments.id'), nullable=False)
    
    # Milvus 信息
    milvus_collection = Column(String(128), comment='Milvus集合名')
    milvus_pk = Column(String(64), comment='Milvus主键')
    
    # Chunk 信息
    chunk_index = Column(Integer, comment='Chunk序号')
    page_start = Column(Integer, comment='起始页码')
    page_end = Column(Integer, comment='结束页码')
    text_content = Column(Text, comment='文本内容（可选缓存）')
    
    # 向量信息（可选）
    embedding_model = Column(String(128), comment='使用的Embedding模型')
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联
    attachment = relationship("Attachment", back_populates="chunks")


class AttachmentMetadataStore:
    """附件元数据存储"""
    
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
        
        # 初始化表
        Base.metadata.create_all(self.engine)
        
        logger.info(f"Attachment metadata store initialized: {host}:{port}/{database}")
    
    def _get_session(self):
        """获取数据库会话"""
        return self.Session()
    
    # ========== CRUD 操作 ==========
    
    def create_attachment(self, metadata: Dict) -> Optional[str]:
        """
        创建附件元数据
        
        Args:
            metadata: 附件元数据字典
        
        Returns:
            file_id
        """
        session = self._get_session()
        try:
            attachment = Attachment(
                file_id=metadata.get("file_id") or self._generate_file_id(),
                file_name=metadata.get("file_name", ""),
                file_type=metadata.get("file_type", ""),
                file_size=metadata.get("file_size", 0),
                file_url=metadata.get("file_url", ""),
                storage_path=metadata.get("storage_path", ""),
                meeting_id=metadata.get("meeting_id"),
                meeting_type=metadata.get("meeting_type"),
                meeting_name=metadata.get("meeting_name"),
                uploader=metadata.get("uploader"),
                department=metadata.get("department"),
                permission_level=metadata.get("permission_level", "internal"),
                allowed_users=metadata.get("allowed_users", []),
                version=metadata.get("version", "1.0"),
                version_notes=metadata.get("version_notes"),
                is_latest=metadata.get("is_latest", True),
                parent_version=metadata.get("parent_version"),
                content_summary=metadata.get("content_summary"),
                keywords=metadata.get("keywords", []),
                page_count=metadata.get("page_count"),
                milvus_collection=metadata.get("milvus_collection"),
                uploaded_at=datetime.utcnow(),
            )
            
            session.add(attachment)
            session.commit()
            
            logger.info(f"Attachment created: {attachment.file_id}")
            return attachment.file_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create attachment: {e}")
            return None
        finally:
            session.close()
    
    def get_attachment(self, file_id: str) -> Optional[Dict]:
        """获取附件元数据"""
        session = self._get_session()
        try:
            attachment = session.query(Attachment).filter(
                Attachment.file_id == file_id,
                Attachment.is_active == True
            ).first()
            
            if attachment:
                return self._attachment_to_dict(attachment)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get attachment: {e}")
            return None
        finally:
            session.close()
    
    def update_attachment(self, file_id: str, updates: Dict) -> bool:
        """更新附件元数据"""
        session = self._get_session()
        try:
            attachment = session.query(Attachment).filter(
                Attachment.file_id == file_id
            ).first()
            
            if not attachment:
                return False
            
            # 更新字段
            for key, value in updates.items():
                if hasattr(attachment, key):
                    setattr(attachment, key, value)
            
            attachment.updated_at = datetime.utcnow()
            session.commit()
            
            logger.info(f"Attachment updated: {file_id}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update attachment: {e}")
            return False
        finally:
            session.close()
    
    def delete_attachment(self, file_id: str, soft_delete: bool = True) -> bool:
        """删除附件元数据"""
        session = self._get_session()
        try:
            attachment = session.query(Attachment).filter(
                Attachment.file_id == file_id
            ).first()
            
            if not attachment:
                return False
            
            if soft_delete:
                attachment.is_active = False
                attachment.updated_at = datetime.utcnow()
            else:
                session.delete(attachment)
            
            session.commit()
            logger.info(f"Attachment deleted: {file_id}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete attachment: {e}")
            return False
        finally:
            session.close()
    
    # ========== 批量查询 ==========
    
    def list_attachments(
        self,
        meeting_id: Optional[str] = None,
        meeting_type: Optional[str] = None,
        file_type: Optional[str] = None,
        uploader: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        列出附件
        """
        session = self._get_session()
        try:
            query = session.query(Attachment).filter(Attachment.is_active == True)
            
            if meeting_id:
                query = query.filter(Attachment.meeting_id == meeting_id)
            if meeting_type:
                query = query.filter(Attachment.meeting_type == meeting_type)
            if file_type:
                query = query.filter(Attachment.file_type == file_type)
            if uploader:
                query = query.filter(Attachment.uploader == uploader)
            
            attachments = query.order_by(Attachment.created_at.desc()).offset(offset).limit(limit).all()
            
            return [self._attachment_to_dict(a) for a in attachments]
            
        except Exception as e:
            logger.error(f"Failed to list attachments: {e}")
            return []
        finally:
            session.close()
    
    def get_attachments_by_meeting(self, meeting_id: str) -> List[Dict]:
        """获取会议关联的所有附件"""
        return self.list_attachments(meeting_id=meeting_id)
    
    # ========== 权限控制 ==========
    
    def check_permission(self, file_id: str, user_id: str, user_dept: str = "") -> bool:
        """
        检查用户是否有权限访问附件
        """
        session = self._get_session()
        try:
            attachment = session.query(Attachment).filter(
                Attachment.file_id == file_id,
                Attachment.is_active == True
            ).first()
            
            if not attachment:
                return False
            
            # 公开文件
            if attachment.permission_level == "public":
                return True
            
            # 指定用户列表
            if attachment.allowed_users and user_id in attachment.allowed_users:
                return True
            
            # 部门权限
            if attachment.permission_level == "internal":
                return True  # 内部人员默认有权限
            
            # 机密文件：需要指定用户或同部门
            if attachment.permission_level == "confidential":
                if attachment.department and user_dept:
                    return attachment.department == user_dept
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check permission: {e}")
            return False
        finally:
            session.close()
    
    def filter_by_permission(
        self,
        file_ids: List[str],
        user_id: str,
        user_dept: str = ""
    ) -> List[str]:
        """过滤有权限的文件ID列表"""
        allowed = []
        for file_id in file_ids:
            if self.check_permission(file_id, user_id, user_dept):
                allowed.append(file_id)
        return allowed
    
    # ========== 版本控制 ==========
    
    def create_new_version(
        self,
        parent_file_id: str,
        new_metadata: Dict
    ) -> Optional[str]:
        """
        创建新版本
        """
        # 获取父版本信息
        parent = self.get_attachment(parent_file_id)
        if not parent:
            return None
        
        # 标记旧版本
        self.update_attachment(parent_file_id, {"is_latest": False})
        
        # 创建新版本
        new_metadata["parent_version"] = parent.get("version")
        new_metadata["version"] = self._increment_version(parent.get("version", "1.0"))
        new_metadata["is_latest"] = True
        
        return self.create_attachment(new_metadata)
    
    def get_version_history(self, file_id: str) -> List[Dict]:
        """获取版本历史"""
        session = self._get_session()
        try:
            # 找到根版本
            current = session.query(Attachment).filter(
                Attachment.file_id == file_id
            ).first()
            
            if not current:
                return []
            
            # 按 meeting_id + file_name 查找所有版本
            versions = session.query(Attachment).filter(
                Attachment.meeting_id == current.meeting_id,
                Attachment.file_name == current.file_name,
                Attachment.is_active == True
            ).order_by(Attachment.created_at.desc()).all()
            
            return [self._attachment_to_dict(v) for v in versions]
            
        except Exception as e:
            logger.error(f"Failed to get version history: {e}")
            return []
        finally:
            session.close()
    
    # ========== Chunk 关联 ==========
    
    def add_chunk_association(
        self,
        file_id: str,
        milvus_collection: str,
        milvus_pk: str,
        chunk_index: int,
        page_start: int = 0,
        page_end: int = 0
    ) -> bool:
        """
        添加 Chunk 关联
        """
        session = self._get_session()
        try:
            attachment = session.query(Attachment).filter(
                Attachment.file_id == file_id
            ).first()
            
            if not attachment:
                return False
            
            chunk = AttachmentChunk(
                attachment_id=attachment.id,
                milvus_collection=milvus_collection,
                milvus_pk=milvus_pk,
                chunk_index=chunk_index,
                page_start=page_start,
                page_end=page_end,
            )
            
            session.add(chunk)
            
            # 更新 chunk 计数
            attachment.chunk_count = session.query(AttachmentChunk).filter(
                AttachmentChunk.attachment_id == attachment.id
            ).count() + 1
            
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add chunk association: {e}")
            return False
        finally:
            session.close()
    
    def get_chunks_by_attachment(self, file_id: str) -> List[Dict]:
        """获取附件的所有 Chunk 关联"""
        session = self._get_session()
        try:
            attachment = session.query(Attachment).filter(
                Attachment.file_id == file_id
            ).first()
            
            if not attachment:
                return []
            
            chunks = session.query(AttachmentChunk).filter(
                AttachmentChunk.attachment_id == attachment.id
            ).order_by(AttachmentChunk.chunk_index).all()
            
            return [
                {
                    "chunk_index": c.chunk_index,
                    "milvus_collection": c.milvus_collection,
                    "milvus_pk": c.milvus_pk,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                }
                for c in chunks
            ]
            
        except Exception as e:
            logger.error(f"Failed to get chunks: {e}")
            return []
        finally:
            session.close()
    
    # ========== 工具方法 ==========
    
    def _generate_file_id(self) -> str:
        """生成文件ID"""
        import uuid
        return f"att_{uuid.uuid4().hex[:16]}"
    
    def _increment_version(self, version: str) -> str:
        """递增版本号"""
        try:
            parts = version.split(".")
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            return f"{major}.{minor + 1}"
        except:
            return "1.0"
    
    def _attachment_to_dict(self, attachment: Attachment) -> Dict:
        """转换为字典"""
        return {
            "file_id": attachment.file_id,
            "file_name": attachment.file_name,
            "file_type": attachment.file_type,
            "file_size": attachment.file_size,
            "file_url": attachment.file_url,
            "meeting_id": attachment.meeting_id,
            "meeting_type": attachment.meeting_type,
            "meeting_name": attachment.meeting_name,
            "uploader": attachment.uploader,
            "department": attachment.department,
            "permission_level": attachment.permission_level,
            "version": attachment.version,
            "is_latest": attachment.is_latest,
            "content_summary": attachment.content_summary,
            "keywords": attachment.keywords,
            "page_count": attachment.page_count,
            "chunk_count": attachment.chunk_count,
            "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
            "updated_at": attachment.updated_at.isoformat() if attachment.updated_at else None,
        }
    
    def close(self):
        """关闭连接"""
        if self.engine:
            self.engine.dispose()
            logger.info("Attachment metadata store closed")


def create_attachment_store_from_env() -> Optional[AttachmentMetadataStore]:
    """从环境变量创建附件元数据存储"""
    import os
    
    # 复用 MySQL 配置
    host = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", "3306"))
    user = os.getenv("MYSQL_USER") or os.getenv("DB_USER", "")
    password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "smart_minutes")
    
    if not user:
        logger.warning("MySQL config not found")
        return None
    
    return AttachmentMetadataStore(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database
    )
