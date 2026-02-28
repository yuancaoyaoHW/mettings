"""
Qwen3-30B-A3B 效果展示脚本
展示使用自部署大模型生成 Schema 扩展字段的效果
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm import complete, stream_complete
from pipelines.ingest import (
    register_extension_field, 
    generate_summary_short,
    generate_keywords,
    generate_sentiment,
    _generate_by_llm
)


def print_section(title):
    """打印章节标题。"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def demo_basic_completion():
    """基础文本生成演示。"""
    print_section("演示 1: 基础文本生成")
    
    prompt = "请介绍一下智能会议纪要系统的核心功能："
    print(f"📝 Prompt: {prompt}\n")
    
    print("🤖 Qwen3-30B-A3B 输出:")
    print("-" * 60)
    
    result = complete(
        prompt,
        system="你是一个专业的会议系统介绍助手。请用中文简洁地回答。"
    )
    print(result)
    print("-" * 60)


def demo_stream_completion():
    """流式文本生成演示。"""
    print_section("演示 2: 流式文本生成（纪要生成场景）")
    
    system_prompt = """你是一个会议纪要撰写助手。请根据会议内容生成简洁的会议纪要。
要求：
1. 提炼关键结论
2. 列出行动项（如有）
3. 使用专业、简洁的语言"""
    
    user_prompt = """
会议内容：
今天讨论了智能纪要系统的 Schema 扩展方案。
主要结论：
1. 采用 Milvus 动态字段模式，支持灵活扩展
2. 使用混合生成策略：规则字段 + LLM 字段
3. 自部署 Qwen3-30B-A3B 模型用于高质量语义生成

行动项：
- 张三负责完成 ingest.py 改造（明天完成）
- 李四负责测试验证（本周五前）
"""
    
    print(f"📝 System Prompt: {system_prompt[:100]}...")
    print(f"📝 User Prompt: {user_prompt[:200]}...\n")
    print("🤖 Qwen3-30B-A3B 流式输出:")
    print("-" * 60)
    
    for token in stream_complete(user_prompt, system=system_prompt):
        print(token, end="", flush=True)
    
    print("\n" + "-" * 60)


def demo_schema_field_generation():
    """Schema 扩展字段生成演示。"""
    print_section("演示 3: Schema 扩展字段生成（核心功能）")
    
    # 模拟会议纪要 chunk
    meeting_chunk = {
        "text": """
        产品周会会议纪要 - 2026年3月15日
        
        参会人：张三（产品经理）、李四（技术负责人）、王五（设计师）
        
        议题1：智能纪要 Schema 扩展方案评审
        结论：同意采用动态字段模式，支持灵活扩展 Schema。自部署 Qwen3-30B-A3B 
        大模型将用于生成高质量语义字段（摘要、关键词、情感等）。
        
        议题2：里程碑排期
        结论：Alpha 版本定于 4 月初发布，包含基础纪要生成和 Schema 扩展功能。
        
        行动项：
        1. 【张三】完成 PRD 文档更新 - 3月18日前
        2. 【李四】完成技术方案评审 - 3月20日前
        3. 【王五】完成 UI 设计稿 - 3月22日前
        """,
        "type": "summary",
        "author": "会议助手",
        "topic": "产品周会"
    }
    
    print("📄 输入会议内容（节选）:")
    print(meeting_chunk["text"][:200] + "...\n")
    
    # 演示各字段生成
    fields_to_demo = [
        ("短摘要", generate_summary_short),
        ("关键词", generate_keywords),
        ("情感倾向", generate_sentiment),
    ]
    
    for field_name, generator_func in fields_to_demo:
        print(f"🔍 生成字段: {field_name}")
        print("-" * 40)
        try:
            result = generator_func(meeting_chunk)
            print(f"✅ 结果: {result}")
        except Exception as e:
            print(f"❌ 错误: {e}")
        print()


def demo_custom_field_registration():
    """自定义字段生成器演示。"""
    print_section("演示 4: 自定义字段生成器（高级用法）")
    
    # 定义一个自定义字段生成器
    def generate_action_count(chunk: dict):
        """统计行动项数量。"""
        text = chunk.get("text", "")
        # 使用 LLM 提取行动项数量
        prompt = f"""请分析以下会议纪要，统计其中明确列出的行动项（待办事项）数量。
只返回数字，不要其他内容。

会议内容：
{text[:1500]}

行动项数量："""
        result = _generate_by_llm(text, prompt)
        try:
            return int(result.strip())
        except:
            return 0
    
    # 注册字段生成器
    register_extension_field("action_count", generate_action_count)
    
    meeting_chunk = {
        "text": """
        技术评审会议纪要
        
        行动项：
        1. 【张三】完成 API 接口设计 - 明天
        2. 【李四】完成数据库迁移脚本 - 本周五
        3. 【王五】完成单元测试覆盖 - 下周一
        4. 【赵六】更新技术文档 - 下周三
        """
    }
    
    print("📄 输入内容:")
    print(meeting_chunk["text"])
    print(f"\n🔍 使用自定义生成器统计行动项数量...")
    print("-" * 40)
    
    count = generate_action_count(meeting_chunk)
    print(f"✅ 检测到行动项数量: {count}")


def demo_batch_processing():
    """批量处理演示。"""
    print_section("演示 5: 批量 Schema 字段生成效果")
    
    chunks = [
        {
            "text": "本周需求评审结论：用户画像功能优先级调整为P0，需要在下个迭代完成。相关技术方案已评审通过。",
            "type": "conclusion",
            "topic": "需求评审"
        },
        {
            "text": "遗留问题：性能压测报告显示并发1000时响应时间超过500ms，需要优化数据库索引和缓存策略。",
            "type": "open_issue",
            "topic": "性能优化"
        },
        {
            "text": "待办：完成智能纪要系统的 Milvus Schema 扩展方案文档，并提交技术评审。负责人：张三，截止：3月20日。",
            "type": "todo",
            "topic": "技术文档"
        }
    ]
    
    print(f"🔄 批量处理 {len(chunks)} 条会议记录...\n")
    
    for i, chunk in enumerate(chunks, 1):
        print(f"--- 记录 {i} ---")
        print(f"原文: {chunk['text'][:60]}...")
        print(f"类型: {chunk['type']}")
        
        # 生成各字段
        summary = generate_summary_short(chunk)
        keywords = generate_keywords(chunk)
        sentiment = generate_sentiment(chunk)
        
        print(f"📌 短摘要: {summary}")
        print(f"🏷️ 关键词: {keywords}")
        print(f"😊 情感: {sentiment}")
        print()


def main():
    """主函数：运行所有演示。"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║   Qwen3-30B-A3B 智能纪要 Schema 扩展效果展示            ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # 检查配置
    from config.settings import settings
    print(f"当前 LLM 配置:")
    print(f"  - Base URL: {settings.llm_base_url or '未配置'}")
    print(f"  - Model: {settings.llm_model_name or '未配置'}")
    print()
    
    if not settings.llm_base_url:
        print("⚠️ 警告: LLM_BASE_URL 未配置，演示可能无法正常输出")
        print("请设置环境变量后再运行:\n")
        print("  export LLM_BASE_URL=http://your-qwen3-server:8000/v1")
        print("  export LLM_MODEL_NAME=Qwen3-30B-A3B")
        print()
    
    # 运行演示
    try:
        demo_basic_completion()
    except Exception as e:
        print(f"❌ 基础生成演示失败: {e}\n")
    
    try:
        demo_stream_completion()
    except Exception as e:
        print(f"❌ 流式生成演示失败: {e}\n")
    
    try:
        demo_schema_field_generation()
    except Exception as e:
        print(f"❌ Schema 字段生成演示失败: {e}\n")
    
    try:
        demo_custom_field_registration()
    except Exception as e:
        print(f"❌ 自定义字段演示失败: {e}\n")
    
    try:
        demo_batch_processing()
    except Exception as e:
        print(f"❌ 批量处理演示失败: {e}\n")
    
    print_section("演示完成")
    print("""
    总结：
    1. ✅ Qwen3-30B-A3B 支持标准 OpenAI 兼容接口
    2. ✅ 支持流式输出，适合实时纪要生成
    3. ✅ 支持 Schema 扩展字段的高质量生成
    4. ✅ 支持自定义字段生成器
    
    下一步：
    - 配置你的 Qwen3-30B-A3B 服务地址
    - 运行实际数据入库测试
    - 调整 prompt 模板优化生成效果
    """)


if __name__ == "__main__":
    main()
