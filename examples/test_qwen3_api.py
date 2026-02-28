"""
Qwen3-30B-A3B API 测试与效果展示
用于验证自部署模型是否正确配置
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm import complete, stream_complete


def test_connection():
    """测试连接是否正常。"""
    print("🔄 测试 Qwen3-30B-A3B 连接...")
    
    from config.settings import settings
    
    if not settings.llm_base_url:
        print("❌ LLM_BASE_URL 未配置")
        return False
    
    print(f"  Base URL: {settings.llm_base_url}")
    print(f"  Model: {settings.llm_model_name or 'default'}")
    
    # 简单测试
    result = complete("你好", system="你是一个 helpful 助手")
    if result:
        print(f"✅ 连接成功！响应示例: {result[:50]}...")
        return True
    else:
        print("❌ 连接失败，请检查配置")
        return False


def test_schema_field_prompts():
    """测试 Schema 字段生成的各种 prompt。"""
    print("\n" + "=" * 60)
    print("测试 Schema 扩展字段生成效果")
    print("=" * 60 + "\n")
    
    test_cases = [
        {
            "name": "短摘要生成",
            "system": "你是一个文本摘要助手。请用不超过50字总结要点。只输出摘要内容。",
            "prompt": """请总结以下会议纪要：

产品周会会议纪要 - 2026年3月15日
参会人：张三（产品经理）、李四（技术负责人）、王五（设计师）

议题1：智能纪要 Schema 扩展方案评审
结论：同意采用动态字段模式，支持灵活扩展 Schema。自部署 Qwen3-30B-A3B 大模型将用于生成高质量语义字段。

议题2：里程碑排期
结论：Alpha 版本定于 4 月初发布，包含基础纪要生成和 Schema 扩展功能。

摘要：""",
            "max_tokens": 100
        },
        {
            "name": "关键词提取",
            "system": "你是一个关键词提取助手。请从文本中提取最多5个关键词，用逗号分隔。只输出关键词。",
            "prompt": """请从以下会议纪要中提取关键词：

智能纪要系统 Schema 扩展技术方案
- 采用 Milvus 动态字段模式
- 支持 sentiment、keywords、summary_short 等扩展字段
- 使用 Qwen3-30B-A3B 模型进行高质量语义生成
- 支持规则生成和 LLM 生成的混合策略

关键词：""",
            "max_tokens": 50
        },
        {
            "name": "情感分析",
            "system": "你是一个情感分析助手。请判断文本情感倾向，只回复 positive/negative/neutral 之一。",
            "prompt": """请判断以下会议纪要的情感倾向：

遗留问题：性能压测报告显示并发1000时响应时间超过500ms，需要优化数据库索引和缓存策略。目前问题比较严重，可能影响上线。

情感倾向：""",
            "max_tokens": 10
        },
        {
            "name": "行动项提取",
            "system": "你是一个行动项提取助手。请从会议纪要中提取行动项，格式：负责人 - 任务 - 截止日期。",
            "prompt": """请提取以下会议纪要中的行动项：

技术评审会议纪要

行动项：
1. 【张三】完成 API 接口设计 - 明天
2. 【李四】完成数据库迁移脚本 - 本周五
3. 【王五】完成单元测试覆盖 - 下周一

提取结果（JSON格式）：
{
  "action_items": [
""",
            "max_tokens": 200
        },
        {
            "name": "会议纪要格式化",
            "system": "你是一个专业的会议纪要撰写助手。请将杂乱的会议记录整理成规范的会议纪要。",
            "prompt": """请将以下会议记录整理成规范的会议纪要：

原始记录：
今天开会讨论了用户画像功能的开发计划。张三说前端需要2周，李四说后端需要3周。
产品同学要求下周必须完成需求评审。王五提到设计稿已经完成，可以评审了。
最后决定下周一开始开发，4月15日上线。张三负责前端，李四负责后端，王五负责设计支持。

请输出：
1. 会议基本信息
2. 讨论要点
3. 结论
4. 行动项（负责人+截止日期）
""",
            "max_tokens": 500
        }
    ]
    
    results = []
    
    for case in test_cases:
        print(f"\n📋 测试: {case['name']}")
        print("-" * 60)
        print(f"System: {case['system'][:60]}...")
        print(f"Prompt: {case['prompt'][:100]}...")
        print("\n🤖 Qwen3-30B-A3B 输出:")
        
        start_time = time.time()
        result = complete(
            case['prompt'],
            system=case['system']
        )
        elapsed = time.time() - start_time
        
        if result:
            print(f"✅ 结果 ({elapsed:.2f}s):")
            print(result)
            results.append({
                "name": case['name'],
                "success": True,
                "time": elapsed,
                "result": result
            })
        else:
            print("❌ 生成失败")
            results.append({
                "name": case['name'],
                "success": False,
                "time": elapsed,
                "result": ""
            })
    
    return results


def test_streaming():
    """测试流式输出效果。"""
    print("\n" + "=" * 60)
    print("测试流式输出（纪要生成场景）")
    print("=" * 60 + "\n")
    
    system = "你是一个会议纪要撰写助手。请根据会议内容生成简洁的纪要。"
    prompt = """
会议内容：
今天讨论了智能纪要系统的 Schema 扩展方案。主要结论包括：
1. 采用 Milvus 动态字段模式，支持灵活扩展
2. 使用混合生成策略：规则字段 + LLM 字段
3. 自部署 Qwen3-30B-A3B 模型用于高质量语义生成

请生成会议纪要：
"""
    
    print(f"Prompt: {prompt[:150]}...\n")
    print("🤖 流式输出:")
    print("-" * 60)
    
    start_time = time.time()
    full_text = ""
    token_count = 0
    
    for token in stream_complete(prompt, system=system):
        print(token, end="", flush=True)
        full_text += token
        token_count += 1
    
    elapsed = time.time() - start_time
    
    print("\n" + "-" * 60)
    print(f"\n✅ 流式输出完成: {token_count} tokens, {elapsed:.2f}s, {token_count/elapsed:.1f} tokens/s")
    
    return {
        "token_count": token_count,
        "time": elapsed,
        "speed": token_count / elapsed if elapsed > 0 else 0
    }


def benchmark_batch():
    """批量性能测试。"""
    print("\n" + "=" * 60)
    print("批量性能测试")
    print("=" * 60 + "\n")
    
    test_prompts = [
        "总结：今天讨论了需求方案，结论是使用方案A。",
        "提取关键词：智能纪要系统、Milvus、动态字段、Qwen3",
        "情感分析：测试结果良好，性能符合预期，准备上线。",
        "生成待办：张三负责API设计，明天完成；李四负责测试，周五完成。",
    ]
    
    times = []
    
    for i, prompt in enumerate(test_prompts, 1):
        print(f"🔄 测试 {i}/{len(test_prompts)}...", end=" ")
        start = time.time()
        result = complete(prompt, system="你是一个文本分析助手")
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"{elapsed:.2f}s - {len(result) if result else 0} chars")
    
    avg_time = sum(times) / len(times)
    print(f"\n📊 平均响应时间: {avg_time:.2f}s")
    print(f"📊 总测试次数: {len(times)}")
    
    return {
        "avg_time": avg_time,
        "min_time": min(times),
        "max_time": max(times),
        "total": len(times)
    }


def main():
    """主函数。"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║   Qwen3-30B-A3B API 测试与效果展示                      ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # 1. 测试连接
    if not test_connection():
        print("\n❌ 连接测试失败，请检查：")
        print("  1. Qwen3-30B-A3B 服务是否已启动")
        print("  2. LLM_BASE_URL 配置是否正确")
        print("  3. 网络连接是否正常")
        return
    
    # 2. 测试 Schema 字段生成
    schema_results = test_schema_field_prompts()
    
    # 3. 测试流式输出
    stream_result = test_streaming()
    
    # 4. 批量性能测试
    benchmark_result = benchmark_batch()
    
    # 5. 汇总报告
    print("\n" + "=" * 60)
    print("测试汇总报告")
    print("=" * 60)
    
    success_count = sum(1 for r in schema_results if r['success'])
    print(f"\n✅ Schema 字段生成测试: {success_count}/{len(schema_results)} 通过")
    
    print(f"\n📊 流式输出性能:")
    print(f"  - 总 tokens: {stream_result['token_count']}")
    print(f"  - 总时间: {stream_result['time']:.2f}s")
    print(f"  - 速度: {stream_result['speed']:.1f} tokens/s")
    
    print(f"\n📊 批量性能测试:")
    print(f"  - 平均响应: {benchmark_result['avg_time']:.2f}s")
    print(f"  - 最快: {benchmark_result['min_time']:.2f}s")
    print(f"  - 最慢: {benchmark_result['max_time']:.2f}s")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试完成！")
    print("=" * 60)
    
    # 保存详细结果
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "schema_results": schema_results,
        "streaming": stream_result,
        "benchmark": benchmark_result
    }
    
    report_file = "qwen3_test_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 详细报告已保存到: {report_file}")


if __name__ == "__main__":
    main()
