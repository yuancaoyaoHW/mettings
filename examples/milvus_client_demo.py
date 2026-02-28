"""
MilvusClient 完整功能演示
展示新的 Milvus 客户端的所有功能
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smart_minutes.adapters.milvus_client import (
    MilvusClient,
    MilvusConfig,
    CollectionSchemaConfig,
    IndexConfig,
    SearchParams,
)


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def demo_connection():
    """演示连接管理"""
    print_section("1. 连接管理")
    
    # 从环境变量创建配置
    config = MilvusConfig(
        uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
        token=os.getenv("MILVUS_TOKEN", ""),
        pool_size=5,
        max_retries=3,
    )
    
    print(f"配置信息:")
    print(f"  - URI: {config.uri}")
    print(f"  - 连接池大小: {config.pool_size}")
    print(f"  - 最大重试: {config.max_retries}")
    
    try:
        client = MilvusClient(config)
        print("\n✅ 客户端创建成功")
        
        # 列出集合
        collections = client.list_collections()
        print(f"现有集合数量: {len(collections)}")
        if collections:
            print(f"集合列表: {collections[:5]}...")  # 最多显示5个
        
        return client
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        return None


def demo_collection_management(client: MilvusClient):
    """演示集合管理"""
    print_section("2. 集合管理")
    
    collection_name = "test_meeting_minutes"
    
    # 删除已存在的集合
    if client.has_collection(collection_name):
        print(f"删除已存在的集合: {collection_name}")
        client.drop_collection(collection_name)
    
    # 创建集合配置
    schema_config = CollectionSchemaConfig(
        collection_name=collection_name,
        description="会议纪要的测试集合",
        vector_dim=768,
        enable_dynamic_field=True,  # 启用动态字段
        scalar_fields=[
            {"name": "source", "dtype": "VARCHAR", "max_length": 64},
            {"name": "type", "dtype": "VARCHAR", "max_length": 64},
            {"name": "topic", "dtype": "VARCHAR", "max_length": 256},
            {"name": "author", "dtype": "VARCHAR", "max_length": 128},
            {"name": "time", "dtype": "VARCHAR", "max_length": 32},
            {"name": "importance", "dtype": "INT32"},  # 整数字段
        ]
    )
    
    index_config = IndexConfig(
        index_type="IVF_FLAT",
        params={"nlist": 128}
    )
    
    print(f"创建集合: {collection_name}")
    print(f"  - 向量维度: {schema_config.vector_dim}")
    print(f"  - 启用动态字段: {schema_config.enable_dynamic_field}")
    print(f"  - 索引类型: {index_config.index_type}")
    
    try:
        client.create_collection(
            schema_config=schema_config,
            index_config=index_config,
            load_immediately=True
        )
        print("✅ 集合创建成功")
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        return
    
    # 获取 Schema
    schema = client.get_schema(collection_name)
    print(f"\n集合 Schema:")
    print(f"  - 描述: {schema.get('description')}")
    print(f"  - 字段数: {len(schema.get('fields', []))}")
    print(f"  - 启用动态字段: {schema.get('enable_dynamic_field')}")
    
    # 获取统计信息
    stats = client.get_collection_stats(collection_name)
    print(f"\n集合统计:")
    print(f"  - 记录数: {stats.get('row_count', 0)}")
    print(f"  - 已加载: {stats.get('is_loaded', False)}")
    
    return collection_name


def demo_data_insertion(client: MilvusClient, collection_name: str):
    """演示数据插入"""
    print_section("3. 数据插入")
    
    # 准备测试数据
    test_data = [
        {
            "text": "产品周会会议纪要：讨论了智能纪要系统的 Schema 扩展方案。",
            "vector": [0.1] * 768,  # 模拟向量
            "source": "minutes",
            "type": "summary",
            "topic": "产品周会",
            "author": "张三",
            "time": "2026-03-15",
            "importance": 5,
            # 动态字段
            "sentiment": "positive",
            "keywords": ["会议纪要", "Schema扩展", "产品周会"],
        },
        {
            "text": "遗留问题：性能压测显示并发1000时响应时间超过500ms。",
            "vector": [0.2] * 768,
            "source": "minutes",
            "type": "open_issue",
            "topic": "性能优化",
            "author": "李四",
            "time": "2026-03-15",
            "importance": 4,
            "sentiment": "negative",
            "keywords": ["性能", "压测", "并发"],
        },
        {
            "text": "待办：完成 Milvus Schema 扩展文档，负责人：张三，截止：3月20日。",
            "vector": [0.3] * 768,
            "source": "minutes",
            "type": "todo",
            "topic": "技术文档",
            "author": "张三",
            "time": "2026-03-15",
            "importance": 4,
            "sentiment": "neutral",
            "keywords": ["待办", "文档", "Schema"],
        },
    ]
    
    print(f"准备插入 {len(test_data)} 条记录")
    
    try:
        ids = client.insert(collection_name, test_data)
        print(f"✅ 插入成功，ID 列表: {ids}")
    except Exception as e:
        print(f"❌ 插入失败: {e}")


def demo_query_and_search(client: MilvusClient, collection_name: str):
    """演示查询和搜索"""
    print_section("4. 查询和搜索")
    
    # 4.1 标量过滤查询
    print("4.1 标量过滤查询")
    print("  查询条件: type == 'summary'")
    
    try:
        results = client.query(
            collection_name=collection_name,
            expr="type == 'summary'",
            output_fields=["text", "topic", "author", "importance"]
        )
        print(f"  ✅ 查询到 {len(results)} 条记录")
        for r in results:
            print(f"     - {r.get('topic')}: {r.get('text')[:30]}...")
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
    
    # 4.2 向量搜索
    print("\n4.2 向量搜索")
    print("  搜索向量: [0.15, 0.15, ...] (模拟)")
    
    try:
        query_vector = [0.15] * 768
        search_params = SearchParams(
            top_k=2,
            output_fields=["text", "topic", "type"]
        )
        
        results = client.search(
            collection_name=collection_name,
            vectors=[query_vector],
            search_params=search_params
        )
        
        print(f"  ✅ 搜索结果:")
        for i, group in enumerate(results):
            print(f"     查询 {i+1}:")
            for hit in group:
                print(f"       - ID: {hit.get('id')}, 距离: {hit.get('distance'):.4f}")
                print(f"         内容: {hit.get('text', '')[:40]}...")
    except Exception as e:
        print(f"  ❌ 搜索失败: {e}")
    
    # 4.3 混合搜索（向量 + 过滤）
    print("\n4.3 混合搜索")
    print("  条件: 向量相似 + importance >= 4")
    
    try:
        query_vector = [0.25] * 768
        search_params = SearchParams(
            top_k=3,
            filter_expr="importance >= 4",
            output_fields=["text", "topic", "importance"]
        )
        
        results = client.hybrid_search(
            collection_name=collection_name,
            vectors=[query_vector],
            filter_expr="importance >= 4",
            top_k=3
        )
        
        print(f"  ✅ 混合搜索结果:")
        for group in results:
            for hit in group:
                print(f"     - {hit.get('topic')} (重要性: {hit.get('importance')})")
    except Exception as e:
        print(f"  ❌ 混合搜索失败: {e}")


def demo_update_and_delete(client: MilvusClient, collection_name: str):
    """演示更新和删除"""
    print_section("5. 更新和删除")
    
    # 先查询获取 ID
    try:
        results = client.query(
            collection_name=collection_name,
            expr="type == 'todo'",
            output_fields=["id"]
        )
        
        if results:
            ids_to_delete = [r.get("id") for r in results if r.get("id")]
            print(f"准备删除 {len(ids_to_delete)} 条 type='todo' 的记录")
            print(f"  ID 列表: {ids_to_delete}")
            
            # 删除
            deleted_count = client.delete_by_ids(collection_name, ids_to_delete)
            print(f"✅ 成功删除 {deleted_count} 条记录")
        else:
            print("没有找到可删除的记录")
    except Exception as e:
        print(f"❌ 删除失败: {e}")


def demo_batch_operations(client: MilvusClient, collection_name: str):
    """演示批量操作"""
    print_section("6. 批量操作")
    
    # 生成批量测试数据
    batch_data = []
    for i in range(100):
        batch_data.append({
            "text": f"批量测试数据 {i}: 这是一条用于测试批量插入的会议纪要。",
            "vector": [0.01 * (i % 100)] * 768,
            "source": "minutes",
            "type": ["summary", "todo", "open_issue"][i % 3],
            "topic": f"批量测试-{i % 10}",
            "author": f"用户{i % 5}",
            "time": "2026-03-15",
            "importance": (i % 5) + 1,
        })
    
    print(f"准备批量插入 {len(batch_data)} 条记录")
    start_time = time.time()
    
    try:
        ids = client.insert(collection_name, batch_data, batch_size=50)
        elapsed = time.time() - start_time
        
        print(f"✅ 批量插入完成")
        print(f"  - 插入数量: {len(ids)}")
        print(f"  - 耗时: {elapsed:.2f}s")
        print(f"  - 速度: {len(ids)/elapsed:.1f} 条/秒")
    except Exception as e:
        print(f"❌ 批量插入失败: {e}")


def demo_schema_migration(client: MilvusClient):
    """演示 Schema 迁移"""
    print_section("7. Schema 迁移")
    
    source = "test_meeting_minutes"
    target = "test_meeting_minutes_v2"
    
    print(f"迁移计划: {source} -> {target}")
    print("  - 启用动态字段")
    print("  - 保留原有数据")
    
    # 检查源集合是否存在
    if not client.has_collection(source):
        print(f"❌ 源集合 '{source}' 不存在，跳过迁移演示")
        return
    
    try:
        manager = SchemaManager(client)
        success = manager.migrate_to_dynamic_field(
            source_collection=source,
            target_collection=target,
            embedding_dim=768
        )
        
        if success:
            print(f"✅ 迁移完成: {target}")
            print("  注意：实际数据迁移需要额外的分批处理逻辑")
        else:
            print("❌ 迁移失败")
    except Exception as e:
        print(f"❌ 迁移出错: {e}")


def demo_resource_cleanup(client: MilvusClient, collection_name: str):
    """演示资源清理"""
    print_section("8. 资源清理")
    
    # 释放集合
    try:
        client.release_collection(collection_name)
        print(f"✅ 集合 '{collection_name}' 已释放")
    except Exception as e:
        print(f"释放失败（可能未加载）: {e}")
    
    # 可选：删除测试集合
    # client.drop_collection(collection_name)
    # print(f"集合 '{collection_name}' 已删除")
    
    # 关闭客户端
    client.close()
    print("✅ 客户端连接已关闭")


def main():
    """主函数"""
    print("""
    ╔══════════════════════════════════════════════════════════════════════╗
    ║                                                                      ║
    ║     MilvusClient 完整功能演示                                       ║
    ║                                                                      ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查 pymilvus
    try:
        import pymilvus
        print(f"pymilvus 版本: {pymilvus.__version__}")
    except ImportError:
        print("❌ 未安装 pymilvus，请先安装: pip install pymilvus")
        return
    
    # 1. 连接管理
    client = demo_connection()
    if client is None:
        print("\n无法连接到 Milvus，请检查：")
        print("  1. Milvus 服务是否运行")
        print("  2. MILVUS_URI 环境变量是否正确设置")
        print("\n示例：")
        print("  export MILVUS_URI=http://localhost:19530")
        return
    
    try:
        # 2. 集合管理
        collection_name = demo_collection_management(client)
        
        if collection_name:
            # 3. 数据插入
            demo_data_insertion(client, collection_name)
            
            # 4. 查询和搜索
            demo_query_and_search(client, collection_name)
            
            # 5. 更新和删除
            demo_update_and_delete(client, collection_name)
            
            # 6. 批量操作
            demo_batch_operations(client, collection_name)
        
        # 7. Schema 迁移
        demo_schema_migration(client)
        
        # 8. 资源清理
        if collection_name:
            demo_resource_cleanup(client, collection_name)
        
    except Exception as e:
        print(f"\n❌ 演示过程中出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("演示完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
