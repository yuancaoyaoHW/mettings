"""
运行所有评测和测试

Usage:
    python tests/evaluation/run_all.py --generate-data
    python tests/evaluation/run_all.py --eval-retrieval
    python tests/evaluation/run_all.py --eval-generation
    python tests/evaluation/run_all.py --e2e-test
    python tests/evaluation/run_all.py --benchmark
    python tests/evaluation/run_all.py --all
"""
import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def generate_sample_data():
    """生成示例数据集"""
    print("=== 生成示例数据集 ===")
    
    from tests.evaluation.retrieval_eval import create_sample_dataset as create_retrieval_data
    from tests.evaluation.generation_eval import create_sample_dataset as create_generation_data
    from tests.evaluation.end_to_end import create_sample_test_cases
    
    create_retrieval_data("tests/evaluation/retrieval_dataset.json", num_samples=50)
    create_generation_data("tests/evaluation/generation_dataset.json", num_samples=20)
    create_sample_test_cases("tests/evaluation/e2e_test_cases.json")
    
    print("\n示例数据集已生成：")
    print("  - tests/evaluation/retrieval_dataset.json")
    print("  - tests/evaluation/generation_dataset.json")
    print("  - tests/evaluation/e2e_test_cases.json")
    print("\n注意：这些只是示例数据，实际评测需要人工标注的真实数据。")


def evaluate_retrieval():
    """评测检索命中率"""
    print("=== 检索命中率评测 ===")
    
    from smart_minutes import SmartMinutesService
    from smart_minutes.adapters.retrieval import RetrievalAdapter
    from tests.evaluation.retrieval_eval import RetrievalEvaluator
    
    # 创建服务（使用 mock 适配器演示）
    retrieval = RetrievalAdapter(client=None, collection_name="")
    service = SmartMinutesService(retrieval, None, None)
    
    evaluator = RetrievalEvaluator(service)
    
    # 加载数据集
    count = evaluator.load_dataset("tests/evaluation/retrieval_dataset.json")
    if count == 0:
        print("未找到数据集，请先运行 --generate-data")
        return
    
    # 执行评测
    metrics = evaluator.evaluate()
    
    # 生成报告
    report = evaluator.generate_report(metrics)
    print(report)
    
    # 保存结果
    import json
    with open("tests/evaluation/retrieval_results.json", 'w') as f:
        json.dump({
            "recall_at_1": metrics.recall_at_1,
            "recall_at_5": metrics.recall_at_5,
            "recall_at_10": metrics.recall_at_10,
            "mrr": metrics.mrr,
            "ndcg_at_5": metrics.ndcg_at_5,
            "ndcg_at_10": metrics.ndcg_at_10,
            "avg_latency_ms": metrics.avg_latency_ms,
        }, f, indent=2)
    print("结果已保存到 tests/evaluation/retrieval_results.json")


def evaluate_generation():
    """评测生成质量"""
    print("=== 生成质量评测 ===")
    
    from smart_minutes import SmartMinutesService
    from smart_minutes.adapters.retrieval import RetrievalAdapter
    from tests.evaluation.generation_eval import GenerationEvaluator
    
    retrieval = RetrievalAdapter(client=None, collection_name="")
    service = SmartMinutesService(retrieval, None, None)
    
    evaluator = GenerationEvaluator(service)
    
    count = evaluator.load_dataset("tests/evaluation/generation_dataset.json")
    if count == 0:
        print("未找到数据集，请先运行 --generate-data")
        return
    
    metrics = evaluator.evaluate()
    report = evaluator.generate_report(metrics)
    print(report)
    
    import json
    with open("tests/evaluation/generation_results.json", 'w') as f:
        json.dump({
            "rouge_1": metrics.rouge_1,
            "rouge_2": metrics.rouge_2,
            "rouge_l": metrics.rouge_l,
            "bleu": metrics.bleu,
            "structure_completeness": metrics.structure_completeness,
        }, f, indent=2)
    print("结果已保存到 tests/evaluation/generation_results.json")


def run_e2e_tests():
    """运行端到端测试"""
    print("=== 端到端测试 ===")
    
    from smart_minutes import SmartMinutesService
    from smart_minutes.adapters.retrieval import RetrievalAdapter
    from tests.evaluation.end_to_end import EndToEndTester
    
    retrieval = RetrievalAdapter(client=None, collection_name="")
    service = SmartMinutesService(retrieval, None, None)
    
    tester = EndToEndTester(service)
    
    count = tester.load_test_cases("tests/evaluation/e2e_test_cases.json")
    if count == 0:
        print("未找到测试用例，请先运行 --generate-data")
        return
    
    results = tester.run_tests()
    report = tester.generate_report(results)
    print(report)
    
    # 统计
    passed = sum(1 for r in results if r.passed)
    print(f"\n总结: {passed}/{len(results)} 通过")


def run_benchmark():
    """运行性能基准测试"""
    print("=== 性能基准测试 ===")
    print("注意：需要真实的服务实例才能运行")
    print("此演示使用 mock 数据")


def main():
    parser = argparse.ArgumentParser(description="运行评测和测试")
    parser.add_argument("--generate-data", action="store_true", help="生成示例数据集")
    parser.add_argument("--eval-retrieval", action="store_true", help="评测检索命中率")
    parser.add_argument("--eval-generation", action="store_true", help="评测生成质量")
    parser.add_argument("--e2e-test", action="store_true", help="运行端到端测试")
    parser.add_argument("--benchmark", action="store_true", help="运行性能基准测试")
    parser.add_argument("--all", action="store_true", help="运行所有评测")
    
    args = parser.parse_args()
    
    if args.generate_data:
        generate_sample_data()
    
    if args.eval_retrieval or args.all:
        evaluate_retrieval()
    
    if args.eval_generation or args.all:
        evaluate_generation()
    
    if args.e2e_test or args.all:
        run_e2e_tests()
    
    if args.benchmark or args.all:
        run_benchmark()
    
    if not any(vars(args).values()):
        parser.print_help()


if __name__ == "__main__":
    main()
