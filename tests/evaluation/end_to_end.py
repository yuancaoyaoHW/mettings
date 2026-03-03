"""
端到端测试

测试完整流程：
1. 数据入库 -> 检索 -> 生成 -> 评估
2. 性能基准测试
3. 压力测试
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from smart_minutes import SmartMinutesService
from smart_minutes.schemas import MinutesRequest, MinutesResponse

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """测试用例"""
    name: str
    description: str
    request: MinutesRequest
    expected_checks: Dict  # 期望检查点


@dataclass
class TestResult:
    """测试结果"""
    name: str
    passed: bool
    duration_ms: float
    error_message: str = ""
    details: Dict = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """基准测试结果"""
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    throughput_qps: float
    total_requests: int
    failed_requests: int


class EndToEndTester:
    """
    端到端测试器
    
    执行完整的测试流程
    """
    
    def __init__(self, service: SmartMinutesService):
        self.service = service
        self.test_cases: List[TestCase] = []
    
    def add_test_case(self, test_case: TestCase):
        """添加测试用例"""
        self.test_cases.append(test_case)
    
    def load_test_cases(self, filepath: str) -> int:
        """从文件加载测试用例"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for item in data:
                self.test_cases.append(TestCase(
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    request=MinutesRequest(**item.get("request", {})),
                    expected_checks=item.get("expected_checks", {})
                ))
            
            logger.info(f"Loaded {len(self.test_cases)} test cases")
            return len(self.test_cases)
            
        except Exception as e:
            logger.error(f"Failed to load test cases: {e}")
            return 0
    
    def run_tests(self) -> List[TestResult]:
        """
        执行所有测试用例
        """
        results = []
        
        for case in self.test_cases:
            logger.info(f"Running test: {case.name}")
            
            start_time = time.time()
            try:
                # 执行请求
                response = self.service.run(case.request)
                duration = (time.time() - start_time) * 1000
                
                # 验证结果
                passed, details = self._verify_response(response, case.expected_checks)
                
                results.append(TestResult(
                    name=case.name,
                    passed=passed,
                    duration_ms=duration,
                    details=details
                ))
                
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                results.append(TestResult(
                    name=case.name,
                    passed=False,
                    duration_ms=duration,
                    error_message=str(e)
                ))
        
        return results
    
    def _verify_response(
        self,
        response: MinutesResponse,
        checks: Dict
    ) -> tuple[bool, Dict]:
        """
        验证响应是否符合期望
        """
        details = {}
        all_passed = True
        
        # 检查是否有内容
        if checks.get("has_content", True):
            has_content = len(response.minutes_content) > 0
            details["has_content"] = has_content
            all_passed &= has_content
        
        # 检查结构化输出
        if "structured_fields" in checks:
            expected_fields = checks["structured_fields"]
            actual_fields = []
            
            if response.structured_output:
                if response.structured_output.meeting_info:
                    actual_fields.append("meeting_info")
                if response.structured_output.topics:
                    actual_fields.append("topics")
                if response.structured_output.materials:
                    actual_fields.append("materials")
            
            fields_match = all(f in actual_fields for f in expected_fields)
            details["structured_fields"] = {
                "expected": expected_fields,
                "actual": actual_fields,
                "match": fields_match
            }
            all_passed &= fields_match
        
        # 检查引用数量
        if "min_references" in checks:
            min_refs = checks["min_references"]
            actual_refs = len(response.references)
            refs_ok = actual_refs >= min_refs
            details["references_count"] = {
                "min_expected": min_refs,
                "actual": actual_refs,
                "ok": refs_ok
            }
            all_passed &= refs_ok
        
        # 检查发言人识别
        if "speaker_count" in checks:
            expected_count = checks["speaker_count"]
            actual_count = len(response.resolved_speakers)
            count_ok = actual_count >= expected_count
            details["speaker_count"] = {
                "expected": expected_count,
                "actual": actual_count,
                "ok": count_ok
            }
            all_passed &= count_ok
        
        # 检查错误
        if checks.get("no_errors", True):
            no_errors = len(response.errors) == 0
            details["no_errors"] = {
                "expected": True,
                "actual": len(response.errors) == 0,
                "errors": [e.message for e in response.errors]
            }
            all_passed &= no_errors
        
        return all_passed, details
    
    def run_benchmark(
        self,
        sample_request: MinutesRequest,
        num_requests: int = 100,
        concurrency: int = 1
    ) -> BenchmarkResult:
        """
        性能基准测试
        
        Args:
            sample_request: 测试请求样本
            num_requests: 总请求数
            concurrency: 并发数
        """
        from concurrent.futures import ThreadPoolExecutor
        
        latencies = []
        failed = 0
        
        def single_request(_) -> float:
            try:
                start = time.time()
                self.service.run(sample_request)
                return (time.time() - start) * 1000
            except Exception as e:
                logger.error(f"Request failed: {e}")
                return -1
        
        start_time = time.time()
        
        if concurrency > 1:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                results = list(executor.map(single_request, range(num_requests)))
        else:
            results = [single_request(i) for i in range(num_requests)]
        
        total_time = time.time() - start_time
        
        # 统计
        for latency in results:
            if latency >= 0:
                latencies.append(latency)
            else:
                failed += 1
        
        if not latencies:
            return BenchmarkResult(
                avg_latency_ms=0,
                p50_latency_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                throughput_qps=0,
                total_requests=num_requests,
                failed_requests=failed
            )
        
        latencies.sort()
        
        return BenchmarkResult(
            avg_latency_ms=sum(latencies) / len(latencies),
            p50_latency_ms=latencies[int(len(latencies) * 0.5)],
            p95_latency_ms=latencies[int(len(latencies) * 0.95)],
            p99_latency_ms=latencies[int(len(latencies) * 0.99)],
            throughput_qps=num_requests / total_time,
            total_requests=num_requests,
            failed_requests=failed
        )
    
    def generate_report(
        self,
        test_results: List[TestResult],
        benchmark: Optional[BenchmarkResult] = None
    ) -> str:
        """生成测试报告"""
        passed = sum(1 for r in test_results if r.passed)
        failed = len(test_results) - passed
        
        report = f"""
=== 端到端测试报告 ===

功能测试:
  总用例数: {len(test_results)}
  通过: {passed}
  失败: {failed}
  通过率: {passed/len(test_results)*100:.1f}%

详细结果:
"""
        for result in test_results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            report += f"  [{status}] {result.name} ({result.duration_ms:.1f}ms)\n"
            if result.error_message:
                report += f"      Error: {result.error_message}\n"
        
        if benchmark:
            report += f"""
性能基准测试:
  总请求数: {benchmark.total_requests}
  失败数: {benchmark.failed_requests}
  
  延迟:
    平均: {benchmark.avg_latency_ms:.1f}ms
    P50:  {benchmark.p50_latency_ms:.1f}ms
    P95:  {benchmark.p95_latency_ms:.1f}ms
    P99:  {benchmark.p99_latency_ms:.1f}ms
  
  吞吐量: {benchmark.throughput_qps:.1f} QPS
"""
        
        report += "\n===========================\n"
        return report


def create_sample_test_cases(output_path: str):
    """生成示例测试用例"""
    cases = [
        {
            "name": "基础纪要生成",
            "description": "测试基本的纪要生成流程",
            "request": {
                "meeting_type": "产品周会",
                "meeting_name": "产品周会第1期",
                "topics": ["需求评审"],
                "draft_text": "讨论了用户画像功能的需求，结论是使用方案A。",
            },
            "expected_checks": {
                "has_content": True,
                "structured_fields": ["meeting_info"],
                "no_errors": True
            }
        },
        {
            "name": "带历史检索的生成",
            "description": "测试结合历史纪要的生成",
            "request": {
                "meeting_type": "技术评审",
                "topics": ["架构方案"],
                "open_issues": ["数据库选型"],
                "conclusions": ["使用MySQL"],
            },
            "expected_checks": {
                "has_content": True,
                "min_references": 1,
                "no_errors": True
            }
        },
        {
            "name": "发言人识别",
            "description": "测试发言人识别功能",
            "request": {
                "meeting_type": "周会",
                "topics": ["进度同步"],
                "oral_names": ["老张", "小李"],
                "draft_text": "老张说进度正常，小李说遇到阻塞。",
            },
            "expected_checks": {
                "speaker_count": 2,
                "no_errors": True
            }
        }
    ]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    
    print(f"Sample test cases created: {output_path}")


if __name__ == "__main__":
    create_sample_test_cases("tests/evaluation/e2e_test_cases.json")
