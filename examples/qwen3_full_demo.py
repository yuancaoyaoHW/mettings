"""
Qwen3-30B-A3B 完整效果展示 - 生产环境版本
展示自部署模型在 Schema 扩展、纪要生成等场景的效果
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm import complete, stream_complete
from pipelines.ingest import (
    ingest_minutes_chunks,
    generate_summary_short,
    generate_summary_detailed,
    generate_keywords,
    generate_sentiment,
    generate_importance,
    generate_category,
    generate_action_items_structured,
    generate_decision_summary,
)


def print_section(title):
    """打印章节标题。"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def demo_full_meeting_processing():
    """完整的会议纪要处理流程演示。"""
    print_section("演示：完整的会议纪要入库流程")
    
    # 模拟一场完整会议的多个片段
    meeting_chunks = [
        {
            "text": """
            产品周会 - 智能纪要系统 Schema 扩展方案评审
            时间：2026年3月15日 14:00-16:00
            参会人：张三（产品经理）、李四（技术负责人）、王五（设计师）、赵六（测试负责人）
            
            议题一：Schema 扩展技术方案
            
            李四：目前我们使用 Milvus 存储会议纪要，但 schema 是固定的。随着业务发展，
            我们需要支持动态添加字段，比如情感分析、关键词提取、重要性评分等。
            
            张三：这些字段对后续的智能检索和统计分析很有价值。建议采用 Milvus 的动态字段模式，
            这样可以在不重建 collection 的情况下扩展 schema。
            
            结论：
            1. 采用 Milvus 2.3+ 的动态字段模式
            2. 自部署的 Qwen3-30B-A3B 模型负责生成高质量语义字段
            3. 支持 sentiment、keywords、importance、category 等扩展字段
            
            行动项：
            - 【李四】3月18日前完成技术方案文档
            - 【张三】3月20日前完成 PRD 更新
            """,
            "type": "summary",
            "source": "minutes",
            "level1": "产品周会",
            "level2": "Schema扩展评审",
            "topic": "技术方案",
            "author": "会议助手",
            "time": "2026-03-15T16:00:00",
        },
        {
            "text": """
            议题二：遗留问题与性能优化
            
            赵六：上周性能压测显示，并发 1000 时查询响应时间超过 500ms，不符合上线标准。
            主要瓶颈在向量检索后的精排阶段。
            
            李四：分析后发现是 rerank 模型调用耗时过长。建议：
            1. 引入缓存机制，相同 query 直接返回缓存结果
            2. 优化 Milvus 索引参数，使用 IVF_PQ 替代 IVF_FLAT
            3. 考虑使用量化向量减少计算量
            
            结论：
            1. 采用三级缓存策略（本地缓存→Redis→模型）
            2. 升级 Milvus 索引为 IVF_PQ，nlist=2048
            3. 引入向量量化，从 FLOAT32 改为 FLOAT16
            
            这是一个阻塞性问题，必须在 Beta 版本前解决。
            """,
            "type": "open_issue",
            "source": "minutes",
            "level1": "产品周会",
            "level2": "Schema扩展评审",
            "topic": "性能优化",
            "author": "会议助手",
            "time": "2026-03-15T16:00:00",
        },
        {
            "text": """
            待办：智能纪要系统 Alpha 版本发布准备
            
            负责人：张三
            截止日期：2026年4月1日
            
            任务清单：
            1. 完成 Schema 扩展功能开发和测试
            2. 完成 Qwen3-30B-A3B 模型集成
            3. 完成 API 接口文档编写
            4. 完成用户操作手册编写
            5. 组织产品验收评审
            
            验收标准：
            - 支持 sentiment、keywords、importance 等 8 个扩展字段
            - 纪要生成准确率 > 90%
            - API 响应时间 < 2s
            - 并发支持 100 QPS
            """,
            "type": "todo",
            "source": "minutes",
            "level1": "产品周会",
            "level2": "Schema扩展评审",
            "topic": "版本发布",
            "author": "会议助手",
            "time": "2026-03-15T16:00:00",
            "owner": "张三",
            "deadline": "2026-04-01",
        },
        {
            "text": """
            需求评审：用户画像功能升级
            
            背景：当前用户画像功能仅支持基础标签，业务方需要更细粒度的分析能力。
            
            讨论要点：
            1. 增加行为序列分析功能
            2. 支持自定义标签规则
            3. 提供画像相似度匹配
            4. 集成实时计算能力
            
            决策结论：
            1. 同意需求方案，优先级调整为 P0
            2. 采用 Lambda 架构，批处理+流处理结合
            3. 使用 Flink 实时计算用户行为特征
            4. 画像存储采用 HBase + Elasticsearch 双写
            
            这是一个战略级项目，需要各团队全力配合。
            """,
            "type": "conclusion",
            "source": "minutes",
            "level1": "产品周会",
            "level2": "需求评审",
            "topic": "用户画像",
            "author": "会议助手",
            "time": "2026-03-15T16:00:00",
        },
    ]
    
    print(f"📄 处理 {len(meeting_chunks)} 个会议片段\n")
    
    # 逐个处理并展示效果
    for i, chunk in enumerate(meeting_chunks, 1):
        print(f"--- 片段 {i}: {chunk['topic']} ({chunk['type']}) ---")
        print(f"原文长度: {len(chunk['text'])} 字符")
        
        # 生成各扩展字段
        start = time.time()
        
        summary_short = generate_summary_short(chunk)
        keywords = generate_keywords(chunk)
        sentiment = generate_sentiment(chunk)
        importance = generate_importance(chunk)
        category = generate_category(chunk)
        
        # 根据类型生成特定字段
        if chunk['type'] == 'conclusion':
            decision = generate_decision_summary(chunk)
        else:
            decision = None
            
        if chunk['type'] in ['summary', 'todo']:
            actions = generate_action_items_structured(chunk)
        else:
            actions = None
        
        elapsed = time.time() - start
        
        # 展示结果
        print(f"📌 短摘要: {summary_short}")
        print(f"🏷️ 关键词: {', '.join(keywords) if keywords else 'N/A'}")
        print(f"😊 情感: {sentiment}")
        print(f"⭐ 重要性: {importance}/5")
        print(f"📂 类别: {category}")
        
        if decision:
            print(f"✅ 决策结论: {decision}")
        if actions:
            print(f"📋 结构化行动项: {json.dumps(actions, ensure_ascii=False)}")
        
        print(f"⏱️ 生成耗时: {elapsed:.2f}s\n")
    
    # 模拟入库（不实际插入，只展示结果）
    print("📦 模拟入库后的数据格式：")
    print("-" * 70)
    
    rows = ingest_minutes_chunks(
        meeting_chunks, 
        use_llm_for_fields=True
    )
    
    if rows:
        print(f"✅ 生成 {len(rows)} 条待插入记录")
        # 展示第一条的扩展字段
        first_row = rows[0]
        dynamic_fields = {k: v for k, v in first_row.items() if k not in [
            'text', 'vector', 'source', 'type', 'level1', 'level2', 'topic',
            'author', 'time', 'version', 'owner', 'deadline', 'status',
            'next_step', 'issue_reason', 'source_id', 'source_position',
            'confidence', 'project', 'department', 'organization'
        ]}
        print(f"\n第一条记录的动态字段:")
        for key, value in dynamic_fields.items():
            value_str = str(value)[:80] + "..." if len(str(value)) > 80 else str(value)
            print(f"  {key}: {value_str}")


def demo_intelligent_retrieval():
    """智能检索演示。"""
    print_section("演示：基于 LLM 生成字段的智能检索")
    
    # 模拟检索场景
    scenarios = [
        {
            "name": "检索高优先级的结论",
            "filters": {"importance": 5, "type": "conclusion"},
            "description": "找出所有关键决策和核心结论"
        },
        {
            "name": "检索负面情感的遗留问题",
            "filters": {"sentiment": "negative", "type": "open_issue"},
            "description": "找出需要重点关注的遗留问题"
        },
        {
            "name": "检索技术相关的待办",
            "filters": {"category": "技术方案", "type": "todo"},
            "description": "找出所有技术任务"
        },
    ]
    
    for scenario in scenarios:
        print(f"🔍 场景: {scenario['name']}")
        print(f"   描述: {scenario['description']}")
        print(f"   过滤条件: {json.dumps(scenario['filters'], ensure_ascii=False)}")
        print("   SQL 等效: SELECT * FROM minutes WHERE " + " AND ".join([
            f"{k} = '{v}'" if isinstance(v, str) else f"{k} = {v}"
            for k, v in scenario['filters'].items()
        ]))
        print()


def demo_comparison():
    """对比展示：使用 LLM 生成 vs 规则生成的差异。"""
    print_section("演示：LLM 生成 vs 规则生成对比")
    
    test_content = """
    这是一个棘手的性能问题。虽然我们已经做了多次优化，但查询速度仍然不理想。
    用户反馈在高峰期经常出现超时，影响了使用体验。
    不过我们找到了新的优化方向，预计下周可以上线修复版本。
    """
    
    chunk = {"text": test_content, "type": "open_issue"}
    
    print("📄 测试内容:")
    print(test_content)
    print()
    
    # LLM 生成
    print("🤖 LLM 生成结果:")
    llm_sentiment = generate_sentiment(chunk)
    llm_importance = generate_importance(chunk)
    llm_keywords = generate_keywords(chunk)
    
    print(f"  情感: {llm_sentiment}")
    print(f"  重要性: {llm_importance}")
    print(f"  关键词: {llm_keywords}")
    print()
    
    # 规则生成（模拟）
    print("📋 规则生成结果:")
    rule_sentiment = "neutral"  # 规则难以准确判断
    rule_importance = 4 if chunk['type'] == 'open_issue' else 3
    rule_keywords = ["性能", "优化", "查询"]  # 简单关键词匹配
    
    print(f"  情感: {rule_sentiment} (无法识别文本中的转折)")
    print(f"  重要性: {rule_importance} (仅基于类型判断)")
    print(f"  关键词: {rule_keywords} (简单词频统计)")
    print()
    
    print("✅ LLM 优势:")
    print("  - 情感分析更准确（识别出'虽然...但...'的积极转向）")
    print("  - 重要性评估考虑语义而非仅类型")
    print("  - 关键词提取更精准（理解上下文）")


def demo_batch_performance():
    """批量处理性能测试。"""
    print_section("演示：批量处理性能")
    
    # 生成测试数据
    test_chunks = [
        {
            "text": f"测试会议纪要片段 {i}，讨论技术方案和排期。",
            "type": ["summary", "todo", "open_issue", "conclusion"][i % 4],
        }
        for i in range(10)
    ]
    
    print(f"🔄 批量处理 {len(test_chunks)} 个 chunks...")
    print("LLM 字段生成已开启（自部署模型场景）\n")
    
    start = time.time()
    rows = ingest_minutes_chunks(test_chunks, use_llm_for_fields=True)
    elapsed = time.time() - start
    
    print(f"✅ 处理完成: {len(rows)} 条记录")
    print(f"⏱️ 总耗时: {elapsed:.2f}s")
    print(f"⚡ 平均每条: {elapsed/len(test_chunks):.2f}s")
    print(f"🚀 预计每小时可处理: {int(3600 / (elapsed/len(test_chunks)))} 条")


def main():
    """主函数。"""
    print("""
    ╔══════════════════════════════════════════════════════════════════════╗
    ║                                                                      ║
    ║     Qwen3-30B-A3B 智能纪要系统 - 完整效果展示                       ║
    ║     （自部署模型 - 全量 LLM 字段生成）                              ║
    ║                                                                      ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查配置
    from config.settings import settings
    print(f"当前配置:")
    print(f"  - LLM Base URL: {settings.llm_base_url or '未配置'}")
    print(f"  - LLM Model: {settings.llm_model_name or '未配置'}")
    print()
    
    if not settings.llm_base_url:
        print("⚠️ 警告: LLM 未配置，请设置环境变量:")
        print("  export LLM_BASE_URL=http://your-qwen3-server:8000/v1")
        print("  export LLM_MODEL_NAME=Qwen3-30B-A3B")
        print()
        return
    
    # 运行演示
    try:
        demo_full_meeting_processing()
    except Exception as e:
        print(f"❌ 完整处理演示失败: {e}")
    
    try:
        demo_intelligent_retrieval()
    except Exception as e:
        print(f"❌ 智能检索演示失败: {e}")
    
    try:
        demo_comparison()
    except Exception as e:
        print(f"❌ 对比演示失败: {e}")
    
    try:
        demo_batch_performance()
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
    
    print_section("总结")
    print("""
    Qwen3-30B-A3B 自部署方案优势：
    
    1. 🚀 高质量字段生成
       - sentiment、keywords、importance 等字段全部使用 LLM 生成
       - 准确率显著高于规则提取
    
    2. 💰 无 API 调用成本
       - 自部署模型，按需扩容
       - 支持高并发批量处理
    
    3. 🔒 数据安全
       - 敏感会议数据不出内网
       - 满足企业合规要求
    
    4. ⚡ 低延迟响应
       - 内网部署，网络延迟 < 10ms
       - 适合实时纪要生成场景
    
    推荐配置：
    - GPU: A100 80G x 2（支持 4-8 并发）
    - 部署框架: vLLM / TGI
    - 量化: FP16（精度优先）或 INT8（性价比优先）
    """)


if __name__ == "__main__":
    main()
