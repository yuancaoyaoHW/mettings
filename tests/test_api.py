"""API 统一门面回归测试：验证工厂创建、路由结构及门面调用链。"""
import pytest
from fastapi.routing import APIRoute

from smart_minutes import SmartMinutesService, MinutesRequest
from smart_minutes.factory import create_service
from api.main import app


class TestFactoryAndFacade:
    """工厂创建与门面调用链。"""

    def test_factory_creates_service(self):
        service = create_service()
        assert isinstance(service, SmartMinutesService)

    def test_service_run_retrieve_only(self):
        """验证门面调用链可用（即使使用 stub 适配器）。"""
        service = create_service()
        req = MinutesRequest(meeting_name="Factory Test", topics=["test"])
        resp = service.run(req, retrieve_only=True)
        assert resp is not None
        assert isinstance(resp.references, list)
        # 验证返回结构符合 MinutesResponse 契约
        assert hasattr(resp, "minutes_content")
        assert hasattr(resp, "mapped_terms")
        assert hasattr(resp, "warnings")


class TestHttpRoutes:
    """HTTP 路由存在性与路径兼容性验证（无需启动完整 ASGI）。"""

    def test_routes_registered(self):
        """验证所有预期端点已注册到 FastAPI 应用。"""
        paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

        # 核心业务端点（v1 推荐路径 + 兼容路径）
        expected = {
            "/health",
            "/api/smart-minutes/generate",
            "/api/v1/smart-minutes/generate",
            "/api/smart-minutes/retrieve",
            "/api/v1/smart-minutes/retrieve",
            "/api/smart-minutes/generate-stream",
            "/api/v1/smart-minutes/generate-stream",
            "/api/smart-minutes/ingest-from-md",
            "/api/v1/smart-minutes/ingest-from-md",
            "/api/schema/info/{collection_name}",
            "/api/v1/schema/info/{collection_name}",
            "/api/schema/register-field",
            "/api/v1/schema/register-field",
            "/api/schema/registered-fields",
            "/api/v1/schema/registered-fields",
            "/api/schema/register-field/{field_name}",
            "/api/v1/schema/register-field/{field_name}",
            "/api/schema/generate-fields",
            "/api/v1/schema/generate-fields",
            "/api/schema/migrate",
            "/api/v1/schema/migrate",
            "/api/schema/preview-field-generation",
            "/api/v1/schema/preview-field-generation",
        }
        for ep in expected:
            assert ep in paths, f"Missing endpoint: {ep}"

    def test_generate_methods(self):
        """验证 generate/retrieve/stream 端点接受 POST 方法。"""
        route_methods = {}
        for route in app.routes:
            if isinstance(route, APIRoute):
                route_methods[route.path] = route.methods

        post_endpoints = [
            "/api/smart-minutes/generate",
            "/api/v1/smart-minutes/generate",
            "/api/smart-minutes/retrieve",
            "/api/v1/smart-minutes/retrieve",
            "/api/smart-minutes/generate-stream",
            "/api/v1/smart-minutes/generate-stream",
            "/api/smart-minutes/ingest-from-md",
            "/api/v1/smart-minutes/ingest-from-md",
        ]
        for ep in post_endpoints:
            assert "POST" in route_methods.get(ep, set()), f"{ep} should accept POST"

    def test_health_get_method(self):
        """验证 health 端点接受 GET 方法。"""
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path == "/health":
                assert "GET" in route.methods
                return
        pytest.fail("/health endpoint not found")

    def test_schema_routes_methods(self):
        """验证 schema 端点方法正确。"""
        route_methods = {}
        for route in app.routes:
            if isinstance(route, APIRoute):
                route_methods[route.path] = route.methods

        # Schema info - GET
        assert "GET" in route_methods.get("/api/schema/info/{collection_name}", set())
        assert "GET" in route_methods.get("/api/v1/schema/info/{collection_name}", set())

        # Register field - POST
        assert "POST" in route_methods.get("/api/schema/register-field", set())
        assert "POST" in route_methods.get("/api/v1/schema/register-field", set())

        # List registered fields - GET
        assert "GET" in route_methods.get("/api/schema/registered-fields", set())
        assert "GET" in route_methods.get("/api/v1/schema/registered-fields", set())

        # Unregister - DELETE
        assert "DELETE" in route_methods.get("/api/schema/register-field/{field_name}", set())
        assert "DELETE" in route_methods.get("/api/v1/schema/register-field/{field_name}", set())


class TestPublicApiSurface:
    """验证对外公开 API 面已收敛。"""

    def test_package_exports(self):
        """smart_minutes 包导出核心门面与契约。"""
        from smart_minutes import (
            SmartMinutesService,
            create_service,
            MinutesRequest,
            MinutesResponse,
            ReferenceItem,
            ErrorItem,
            RealtimeSpeakerInput,
        )
        # 确保主要类可访问
        assert SmartMinutesService is not None
        assert create_service is not None
        assert MinutesRequest is not None
        assert MinutesResponse is not None
