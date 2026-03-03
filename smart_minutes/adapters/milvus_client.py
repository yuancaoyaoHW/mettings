"""
完整的 Milvus 客户端封装
提供连接池、CRUD、批量操作、Schema 管理、索引管理等功能
"""
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

# 尝试导入 pymilvus
try:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        MilvusClient,
        connections,
        utility,
    )
    from pymilvus.exceptions import MilvusException, ErrorCode
    HAS_PYMILVUS = True
except ImportError:
    HAS_PYMILVUS = False
    # 创建占位类以避免导入错误
    class MilvusException(Exception):
        pass
    class ErrorCode:
        pass

logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================

@dataclass
class MilvusConfig:
    """Milvus 连接配置"""
    host: str = "localhost"
    port: int = 19530
    uri: str = ""  # 优先使用 uri（如 http://localhost:19530）
    token: str = ""  # 认证 token
    db_name: str = "default"
    
    # 连接池配置
    pool_size: int = 10
    wait_timeout: float = 5.0
    
    # 重试配置
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # 超时配置
    connect_timeout: float = 10.0
    query_timeout: float = 30.0


@dataclass
class CollectionSchemaConfig:
    """集合 Schema 配置"""
    collection_name: str
    description: str = ""
    
    # 向量配置
    vector_dim: int = 768
    vector_field: str = "vector"
    metric_type: str = "COSINE"  # L2, IP, COSINE
    
    # 主键配置
    primary_field: str = "id"
    auto_id: bool = True
    
    # 文本字段
    text_field: str = "text"
    max_text_length: int = 65535
    
    # 动态字段
    enable_dynamic_field: bool = True
    
    # 自定义标量字段
    scalar_fields: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class IndexConfig:
    """索引配置"""
    index_type: str = "IVF_FLAT"  # IVF_FLAT, IVF_PQ, HNSW, FLAT
    params: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.params:
            # 默认参数
            if self.index_type == "IVF_FLAT":
                self.params = {"nlist": 128}
            elif self.index_type == "IVF_PQ":
                self.params = {"nlist": 128, "m": 16, "nbits": 8}
            elif self.index_type == "HNSW":
                self.params = {"M": 16, "efConstruction": 200}


@dataclass
class SearchParams:
    """搜索参数"""
    top_k: int = 10
    nprobe: int = 128  # IVF 索引使用
    ef: int = 200  # HNSW 索引使用
    radius: Optional[float] = None  # 范围搜索
    output_fields: Optional[List[str]] = None
    filter_expr: Optional[str] = None


# ==================== 异常类 ====================

class MilvusClientError(Exception):
    """Milvus 客户端错误"""
    pass


class ConnectionError(MilvusClientError):
    """连接错误"""
    pass


class CollectionNotFoundError(MilvusClientError):
    """集合不存在"""
    pass


class SchemaError(MilvusClientError):
    """Schema 错误"""
    pass


# ==================== 连接池 ====================

class ConnectionPool:
    """简单的 Milvus 连接池"""
    
    def __init__(self, config: MilvusConfig):
        self.config = config
        self._lock = threading.Lock()
        self._connections: Dict[str, Any] = {}
        self._in_use: set = set()
        self._connection_count = 0
        
    def _create_connection(self, alias: str) -> Any:
        """创建新连接"""
        if not HAS_PYMILVUS:
            raise ImportError("pymilvus is not installed")
        
        try:
            if self.config.uri:
                connections.connect(
                    alias=alias,
                    uri=self.config.uri,
                    token=self.config.token,
                    db_name=self.config.db_name,
                )
            else:
                connections.connect(
                    alias=alias,
                    host=self.config.host,
                    port=self.config.port,
                    db_name=self.config.db_name,
                )
            return connections._fetch_handler(alias)
        except Exception as e:
            logger.error(f"Failed to create connection: {e}")
            raise ConnectionError(f"Failed to connect to Milvus: {e}")
    
    @contextmanager
    def acquire(self):
        """获取连接上下文"""
        alias = None
        start_time = time.time()
        
        while time.time() - start_time < self.config.wait_timeout:
            with self._lock:
                # 寻找空闲连接
                for conn_alias in list(self._connections.keys()):
                    if conn_alias not in self._in_use:
                        self._in_use.add(conn_alias)
                        alias = conn_alias
                        break
                
                # 创建新连接
                if alias is None and self._connection_count < self.config.pool_size:
                    alias = f"conn_{self._connection_count}"
                    self._connections[alias] = self._create_connection(alias)
                    self._in_use.add(alias)
                    self._connection_count += 1
            
            if alias:
                break
            
            time.sleep(0.1)
        
        if alias is None:
            raise ConnectionError("Connection pool exhausted")
        
        try:
            yield alias
        finally:
            with self._lock:
                self._in_use.discard(alias)
    
    def close_all(self):
        """关闭所有连接"""
        with self._lock:
            for alias in list(self._connections.keys()):
                try:
                    connections.disconnect(alias)
                except:
                    pass
            self._connections.clear()
            self._in_use.clear()
            self._connection_count = 0


# ==================== Milvus 客户端 ====================

class MilvusClient:
    """
    完整的 Milvus 客户端封装
    
    功能：
    - 连接池管理
    - 集合管理（创建、删除、加载、释放）
    - Schema 管理
    - 索引管理
    - 数据操作（插入、删除、查询）
    - 向量搜索（ANN、范围搜索、混合搜索）
    - 批量操作
    """
    
    def __init__(self, config: Optional[MilvusConfig] = None):
        self.config = config or MilvusConfig()
        self.pool = ConnectionPool(self.config)
        self._local = threading.local()
        
        if not HAS_PYMILVUS:
            logger.warning("pymilvus is not installed, MilvusClient will not work")
    
    # ---------- 连接管理 ----------
    
    def close(self):
        """关闭客户端"""
        self.pool.close_all()
        logger.info("Milvus client closed")
    
    def _get_collection(self, name: str) -> "Collection":
        """获取集合对象"""
        if not self.has_collection(name):
            raise CollectionNotFoundError(f"Collection '{name}' not found")
        return Collection(name)
    
    def _with_retry(self, operation, *args, **kwargs):
        """带重试的操作"""
        last_error = None
        
        for attempt in range(self.config.max_retries):
            try:
                return operation(*args, **kwargs)
            except MilvusException as e:
                last_error = e
                if e.code == ErrorCode.RATE_LIMIT:
                    time.sleep(self.config.retry_delay * (attempt + 1))
                    continue
                raise
            except Exception as e:
                last_error = e
                time.sleep(self.config.retry_delay)
        
        raise MilvusClientError(f"Operation failed after {self.config.max_retries} retries: {last_error}")
    
    # ---------- 集合管理 ----------
    
    def create_collection(
        self,
        schema_config: CollectionSchemaConfig,
        index_config: Optional[IndexConfig] = None,
        load_immediately: bool = False
    ) -> bool:
        """
        创建集合
        
        Args:
            schema_config: Schema 配置
            index_config: 索引配置，None 则不创建索引
            load_immediately: 是否立即加载到内存
        """
        if not HAS_PYMILVUS:
            raise ImportError("pymilvus is not installed")
        
        if self.has_collection(schema_config.collection_name):
            logger.warning(f"Collection '{schema_config.collection_name}' already exists")
            return False
        
        try:
            # 创建字段
            fields = [
                FieldSchema(
                    name=schema_config.primary_field,
                    dtype=DataType.INT64,
                    is_primary=True,
                    auto_id=schema_config.auto_id,
                    description="Primary key"
                ),
                FieldSchema(
                    name=schema_config.text_field,
                    dtype=DataType.VARCHAR,
                    max_length=schema_config.max_text_length,
                    description="Text content"
                ),
                FieldSchema(
                    name=schema_config.vector_field,
                    dtype=DataType.FLOAT_VECTOR,
                    dim=schema_config.vector_dim,
                    description="Vector embedding"
                ),
            ]
            
            # 添加自定义标量字段
            for field_def in schema_config.scalar_fields:
                field_schema = self._create_field_schema(field_def)
                fields.append(field_schema)
            
            # 创建 schema
            schema = CollectionSchema(
                fields=fields,
                description=schema_config.description,
                enable_dynamic_field=schema_config.enable_dynamic_field
            )
            
            # 创建集合
            collection = Collection(
                name=schema_config.collection_name,
                schema=schema,
                using="default"
            )
            
            logger.info(f"Collection '{schema_config.collection_name}' created")
            
            # 创建索引
            if index_config:
                self.create_index(
                    schema_config.collection_name,
                    schema_config.vector_field,
                    schema_config.metric_type,
                    index_config
                )
            
            # 加载集合
            if load_immediately:
                collection.load()
                logger.info(f"Collection '{schema_config.collection_name}' loaded")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise SchemaError(f"Failed to create collection: {e}")
    
    def _create_field_schema(self, field_def: Dict[str, Any]) -> FieldSchema:
        """根据定义创建字段 schema"""
        name = field_def["name"]
        dtype_str = field_def["dtype"].upper()
        
        dtype_map = {
            "INT8": DataType.INT8,
            "INT16": DataType.INT16,
            "INT32": DataType.INT32,
            "INT64": DataType.INT64,
            "FLOAT": DataType.FLOAT,
            "DOUBLE": DataType.DOUBLE,
            "BOOL": DataType.BOOL,
            "VARCHAR": DataType.VARCHAR,
            "JSON": DataType.JSON,
            "ARRAY": DataType.ARRAY,
        }
        
        dtype = dtype_map.get(dtype_str, DataType.VARCHAR)
        
        kwargs = {
            "name": name,
            "dtype": dtype,
            "description": field_def.get("description", ""),
        }
        
        if dtype == DataType.VARCHAR:
            kwargs["max_length"] = field_def.get("max_length", 512)
        
        if dtype == DataType.ARRAY:
            kwargs["element_type"] = dtype_map.get(
                field_def.get("element_type", "VARCHAR").upper(),
                DataType.VARCHAR
            )
            kwargs["max_capacity"] = field_def.get("max_capacity", 100)
        
        return FieldSchema(**kwargs)
    
    def drop_collection(self, name: str) -> bool:
        """删除集合"""
        try:
            if self.has_collection(name):
                utility.drop_collection(name)
                logger.info(f"Collection '{name}' dropped")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to drop collection: {e}")
            raise
    
    def has_collection(self, name: str) -> bool:
        """检查集合是否存在"""
        try:
            return utility.has_collection(name)
        except Exception as e:
            logger.error(f"Failed to check collection: {e}")
            return False
    
    def list_collections(self) -> List[str]:
        """列出所有集合"""
        try:
            return utility.list_collections()
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    def get_collection_stats(self, name: str) -> Dict[str, Any]:
        """获取集合统计信息"""
        try:
            collection = self._get_collection(name)
            return {
                "name": name,
                "row_count": collection.num_entities,
                "is_loaded": collection.is_loaded,
                "partitions": [p.name for p in collection.partitions],
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}
    
    def load_collection(self, name: str) -> bool:
        """加载集合到内存"""
        try:
            collection = self._get_collection(name)
            if not collection.is_loaded:
                collection.load()
                logger.info(f"Collection '{name}' loaded")
            return True
        except Exception as e:
            logger.error(f"Failed to load collection: {e}")
            raise
    
    def release_collection(self, name: str) -> bool:
        """释放集合"""
        try:
            collection = self._get_collection(name)
            if collection.is_loaded:
                collection.release()
                logger.info(f"Collection '{name}' released")
            return True
        except Exception as e:
            logger.error(f"Failed to release collection: {e}")
            raise
    
    # ---------- Schema 管理 ----------
    
    def get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """获取集合 schema"""
        try:
            collection = self._get_collection(name)
            schema = collection.schema
            
            return {
                "collection_name": name,
                "description": schema.description,
                "fields": [
                    {
                        "name": f.name,
                        "dtype": str(f.dtype),
                        "is_primary": f.is_primary,
                        "auto_id": f.auto_id,
                        "description": f.description,
                    }
                    for f in schema.fields
                ],
                "enable_dynamic_field": schema.enable_dynamic_field,
            }
        except Exception as e:
            logger.error(f"Failed to get schema: {e}")
            return None
    
    # ---------- 索引管理 ----------
    
    def create_index(
        self,
        collection_name: str,
        field_name: str,
        metric_type: str = "COSINE",
        index_config: Optional[IndexConfig] = None
    ) -> bool:
        """创建索引"""
        try:
            collection = self._get_collection(collection_name)
            
            index_config = index_config or IndexConfig()
            
            index_params = {
                "metric_type": metric_type,
                "index_type": index_config.index_type,
                "params": index_config.params,
            }
            
            collection.create_index(field_name, index_params)
            logger.info(f"Index created for '{collection_name}.{field_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            raise
    
    def drop_index(self, collection_name: str, field_name: str) -> bool:
        """删除索引"""
        try:
            collection = self._get_collection(collection_name)
            collection.drop_index(field_name)
            logger.info(f"Index dropped for '{collection_name}.{field_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to drop index: {e}")
            raise
    
    def has_index(self, collection_name: str, field_name: str) -> bool:
        """检查是否存在索引"""
        try:
            collection = self._get_collection(collection_name)
            return len(collection.indexes) > 0
        except Exception as e:
            logger.error(f"Failed to check index: {e}")
            return False
    
    # ---------- 数据插入 ----------
    
    def insert(
        self,
        collection_name: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> List[Union[int, str]]:
        """
        插入数据
        
        Args:
            collection_name: 集合名称
            data: 数据列表
            batch_size: 批处理大小
        
        Returns:
            插入的 ID 列表
        """
        try:
            collection = self._get_collection(collection_name)
            
            # 确保集合已加载
            if not collection.is_loaded:
                collection.load()
            
            all_ids = []
            
            # 分批插入
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                
                # 转换数据格式
                entities = self._convert_to_entities(collection, batch)
                
                # 插入
                result = collection.insert(entities)
                all_ids.extend(result.primary_keys)
                
                logger.debug(f"Inserted {len(batch)} entities into '{collection_name}'")
            
            # 刷新以确保数据持久化
            collection.flush()
            
            logger.info(f"Inserted {len(data)} entities into '{collection_name}'")
            return all_ids
            
        except Exception as e:
            logger.error(f"Failed to insert data: {e}")
            raise
    
    def _convert_to_entities(
        self,
        collection: "Collection",
        data: List[Dict[str, Any]]
    ) -> List[List[Any]]:
        """将字典列表转换为 Milvus 实体格式"""
        schema = collection.schema
        entities = []
        
        for field in schema.fields:
            if field.auto_id:
                continue  # 跳过自增主键
            
            field_name = field.name
            values = []
            
            for item in data:
                value = item.get(field_name)
                
                # 处理动态字段
                if value is None and schema.enable_dynamic_field:
                    # 尝试从 $meta 获取
                    value = item.get(f"${field_name}")
                
                values.append(value)
            
            entities.append(values)
        
        return entities
    
    def upsert(
        self,
        collection_name: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> List[Union[int, str]]:
        """
        插入或更新数据（Milvus 2.3+ 支持 upsert）
        """
        try:
            collection = self._get_collection(collection_name)
            
            if not collection.is_loaded:
                collection.load()
            
            all_ids = []
            
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                entities = self._convert_to_entities(collection, batch)
                
                # 使用 upsert
                result = collection.upsert(entities)
                all_ids.extend(result.primary_keys)
            
            collection.flush()
            logger.info(f"Upserted {len(data)} entities into '{collection_name}'")
            return all_ids
            
        except Exception as e:
            logger.error(f"Failed to upsert data: {e}")
            # 回退到 insert（如果主键冲突会失败）
            return self.insert(collection_name, data, batch_size)
    
    # ---------- 数据删除 ----------
    
    def delete(
        self,
        collection_name: str,
        expr: str
    ) -> int:
        """
        删除数据
        
        Args:
            collection_name: 集合名称
            expr: 删除条件表达式，如 "id in [1, 2, 3]" 或 "age > 18"
        
        Returns:
            删除的行数
        """
        try:
            collection = self._get_collection(collection_name)
            
            if not collection.is_loaded:
                collection.load()
            
            result = collection.delete(expr)
            collection.flush()
            
            deleted_count = len(result) if hasattr(result, '__len__') else 0
            logger.info(f"Deleted {deleted_count} entities from '{collection_name}'")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete data: {e}")
            raise
    
    def delete_by_ids(
        self,
        collection_name: str,
        ids: List[Union[int, str]]
    ) -> int:
        """根据 ID 删除"""
        if not ids:
            return 0
        
        # 构建删除表达式
        id_str = ", ".join([str(id_) for id_ in ids])
        expr = f"id in [{id_str}]"
        
        return self.delete(collection_name, expr)
    
    # ---------- 数据查询 ----------
    
    def get(
        self,
        collection_name: str,
        ids: List[Union[int, str]],
        output_fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        根据 ID 获取数据
        """
        try:
            collection = self._get_collection(collection_name)
            
            if not collection.is_loaded:
                collection.load()
            
            # 默认返回所有字段
            if output_fields is None:
                output_fields = [f.name for f in collection.schema.fields]
                if collection.schema.enable_dynamic_field:
                    output_fields.append("$meta")
            
            result = collection.get(
                ids=ids,
                output_fields=output_fields
            )
            
            return self._convert_to_dicts(result, output_fields)
            
        except Exception as e:
            logger.error(f"Failed to get data: {e}")
            return []
    
    def query(
        self,
        collection_name: str,
        expr: str,
        output_fields: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        标量过滤查询
        """
        try:
            collection = self._get_collection(collection_name)
            
            if not collection.is_loaded:
                collection.load()
            
            if output_fields is None:
                output_fields = [f.name for f in collection.schema.fields]
                if collection.schema.enable_dynamic_field:
                    output_fields.append("$meta")
            
            result = collection.query(
                expr=expr,
                output_fields=output_fields,
                limit=limit,
                offset=offset
            )
            
            return self._convert_to_dicts(result, output_fields)
            
        except Exception as e:
            logger.error(f"Failed to query data: {e}")
            return []
    
    def _convert_to_dicts(
        self,
        result: List[Any],
        output_fields: List[str]
    ) -> List[Dict[str, Any]]:
        """将 Milvus 结果转换为字典列表"""
        dicts = []
        for item in result:
            if isinstance(item, dict):
                dicts.append(item)
            else:
                # 处理 tuple 格式
                dicts.append(dict(zip(output_fields, item)))
        return dicts
    
    # ---------- 向量搜索 ----------
    
    def search(
        self,
        collection_name: str,
        vectors: List[List[float]],
        vector_field: str = "vector",
        search_params: Optional[SearchParams] = None,
        **kwargs
    ) -> List[List[Dict[str, Any]]]:
        """
        向量相似度搜索（ANN）
        
        Args:
            collection_name: 集合名称
            vectors: 查询向量列表
            vector_field: 向量字段名
            search_params: 搜索参数
            **kwargs: 额外参数（兼容旧接口）
        
        Returns:
            每组向量的搜索结果列表
        """
        search_params = search_params or SearchParams()
        
        try:
            collection = self._get_collection(collection_name)
            
            if not collection.is_loaded:
                collection.load()
            
            # 构建输出字段
            output_fields = search_params.output_fields or [
                f.name for f in collection.schema.fields
                if not f.dtype == DataType.FLOAT_VECTOR
            ]
            if collection.schema.enable_dynamic_field:
                output_fields.append("$meta")
            
            # 构建搜索参数
            param = {
                "metric_type": kwargs.get("metric_type", "COSINE"),
                "params": {
                    "nprobe": search_params.nprobe,
                    "ef": search_params.ef,
                }
            }
            
            # 执行搜索
            results = collection.search(
                data=vectors,
                anns_field=vector_field,
                param=param,
                limit=search_params.top_k,
                expr=search_params.filter_expr or kwargs.get("expr"),
                output_fields=output_fields,
                timeout=self.config.query_timeout
            )
            
            # 转换结果格式
            return self._convert_search_results(results)
            
        except Exception as e:
            logger.error(f"Failed to search: {e}")
            return [[] for _ in vectors]
    
    def _convert_search_results(
        self,
        results: List[Any]
    ) -> List[List[Dict[str, Any]]]:
        """转换搜索结果为标准格式"""
        converted = []
        
        for result_group in results:
            group = []
            for hit in result_group:
                item = {
                    "id": hit.id,
                    "distance": hit.distance,
                    "score": 1 - hit.distance if hit.distance <= 1 else hit.distance,
                }
                # 添加其他字段
                if hasattr(hit, 'entity') and hit.entity:
                    item.update(hit.entity.to_dict())
                group.append(item)
            converted.append(group)
        
        return converted
    
    def hybrid_search(
        self,
        collection_name: str,
        vectors: List[List[float]],
        vector_field: str = "vector",
        filter_expr: str = "",
        rerank: bool = False,
        **kwargs
    ) -> List[List[Dict[str, Any]]]:
        """
        混合搜索：向量搜索 + 标量过滤
        """
        search_params = SearchParams(
            filter_expr=filter_expr,
            **kwargs
        )
        return self.search(
            collection_name,
            vectors,
            vector_field,
            search_params
        )
    
    def search_by_text(
        self,
        collection_name: str,
        texts: List[str],
        embedding_func: callable,
        **kwargs
    ) -> List[List[Dict[str, Any]]]:
        """
        文本搜索（自动转换为向量）
        """
        # 将文本转换为向量
        vectors = [embedding_func(text) for text in texts]
        return self.search(collection_name, vectors, **kwargs)
    
    # ---------- 批量操作 ----------
    
    def batch_insert(
        self,
        collection_name: str,
        data_iterator: Iterator[List[Dict[str, Any]]],
        batch_size: int = 1000
    ) -> int:
        """
        批量插入（支持大数据量）
        
        Args:
            collection_name: 集合名称
            data_iterator: 数据迭代器
            batch_size: 每批大小
        
        Returns:
            插入总数
        """
        total = 0
        
        for batch in data_iterator:
            ids = self.insert(collection_name, batch, batch_size)
            total += len(ids)
            logger.info(f"Batch inserted: {total} total")
        
        return total
    
    def bulk_delete(
        self,
        collection_name: str,
        exprs: List[str]
    ) -> int:
        """批量删除"""
        total = 0
        for expr in exprs:
            count = self.delete(collection_name, expr)
            total += count
        return total


# ==================== 便捷函数 ====================

def create_milvus_client_from_env() -> MilvusClient:
    """从环境变量创建 Milvus 客户端"""
    import os
    
    uri = os.getenv("MILVUS_URI", "")
    host = os.getenv("MILVUS_HOST") or os.getenv("MILVUS_IP", "localhost")
    port = int(os.getenv("MILVUS_PORT", "19530"))
    config = MilvusConfig(
        uri=uri,
        token=os.getenv("MILVUS_TOKEN", ""),
        host=host,
        port=port,
        db_name=os.getenv("MILVUS_DB_NAME", "default"),
        pool_size=int(os.getenv("MILVUS_POOL_SIZE", "10")),
        max_retries=int(os.getenv("MILVUS_MAX_RETRIES", "3")),
    )
    
    return MilvusClient(config)


# 全局客户端实例
_global_client: Optional[MilvusClient] = None
_global_lock = threading.Lock()


def get_milvus_client() -> MilvusClient:
    """获取全局 Milvus 客户端（单例）"""
    global _global_client
    
    if _global_client is None:
        with _global_lock:
            if _global_client is None:
                _global_client = create_milvus_client_from_env()
    
    return _global_client
