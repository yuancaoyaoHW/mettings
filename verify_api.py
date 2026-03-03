#!/usr/bin/env python3
"""API 统一门面验证脚本 - 无需 pytest"""
import sys

def test_factory():
    """测试工厂创建服务"""
    print("测试 1: 工厂创建服务...")
    from smart_minutes.factory import create_service
    from smart_minutes import SmartMinutesService
    service = create_service()
    assert isinstance(service, SmartMinutesService), "工厂应返回 SmartMinutesService"
    print("✓ 工厂创建服务成功")
    return True

def test_facade_run():
    """测试门面调用链"""
    print("\n测试 2: 门面调用链...")
    from smart_minutes import SmartMinutesService, MinutesRequest
    from smart_minutes.factory import create_service
    service = create_service()
    req = MinutesRequest(meeting_name="Test", topics=["topic1"])
    resp = service.run(req, retrieve_only=True)
    assert resp is not None, "响应不应为空"
    assert hasattr(resp, "references"), "响应应有 references"
    assert hasattr(resp, "minutes_content"), "响应应有 minutes_content"
    print("✓ 门面调用链正常")
    return True

def test_package_exports():
    """测试包导出"""
    print("\n测试 3: 包导出...")
    from smart_minutes import (
        SmartMinutesService,
        create_service,
        MinutesRequest,
        MinutesResponse,
        ReferenceItem,
        ErrorItem,
    )
    print("✓ 核心 API 已导出")
    return True

def test_routes():
    """测试路由注册"""
    print("\n测试 4: HTTP 路由...")
    from api.main import app
    from fastapi.routing import APIRoute
    paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    required = {
        "/api/v1/smart-minutes/generate",
        "/api/v1/smart-minutes/retrieve",
        "/api/v1/smart-minutes/generate-stream",
        "/api/smart-minutes/generate",  # 兼容路径
    }
    for p in required:
        assert p in paths, f"缺少路由: {p}"
    print(f"✓ 路由已注册 ({len(paths)} 个端点)")
    return True

def main():
    print("="*50)
    print("API 统一门面验证")
    print("="*50)
    
    tests = [
        test_factory,
        test_facade_run,
        test_package_exports,
        test_routes,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} 失败: {e}")
            failed += 1
    
    print("\n" + "="*50)
    print(f"结果: {passed} 通过, {failed} 失败")
    print("="*50)
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
