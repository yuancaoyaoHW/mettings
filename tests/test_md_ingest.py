"""MD 文件入库模块测试。"""
import tempfile
from pathlib import Path

import pytest

from pipelines.md_ingest import (
    _split_md_by_headers,
    _parse_md_to_chunks,
    ingest_from_md,
)


class TestSplitMdByHeaders:
    """MD 按标题切分。"""

    def test_split_by_h2(self):
        content = """## 议题一
内容A

## 议题二
内容B
"""
        sections = _split_md_by_headers(content)
        assert len(sections) == 2
        assert sections[0] == ("议题一", "内容A")
        assert sections[1] == ("议题二", "内容B")

    def test_split_by_h1(self):
        content = """# 会议纪要
总览

## 详情
详情内容
"""
        sections = _split_md_by_headers(content)
        assert len(sections) >= 2
        assert sections[0][0] == "会议纪要"

    def test_no_headers_returns_single_section(self):
        content = "无标题的整段内容"
        sections = _split_md_by_headers(content)
        assert len(sections) == 1
        assert sections[0] == ("", "无标题的整段内容")


class TestIngestFromMd:
    """ingest_from_md 集成测试（无真实 Milvus）。"""

    def test_file_path_unconfigured(self):
        """FILE_PATH 未配置时返回错误。"""
        result = ingest_from_md(
            "kb1", "doc1",
            file_path="",
            collection_name="coll",
            client=None,
        )
        assert result["success"] is False
        assert "FILE_PATH" in result["errors"][0] or "未配置" in result["errors"][0]
        assert result["ingested_count"] == 0

    def test_path_not_exists(self):
        """路径不存在时返回错误。"""
        result = ingest_from_md(
            "kb1", "doc1",
            file_path="/nonexistent/path",
            collection_name="coll",
            client=None,
        )
        assert result["success"] is False
        assert "路径不存在" in result["errors"][0] or "无 .md 文件" in result["errors"][0]

    def test_no_md_files(self):
        """vlm 目录存在但无 .md 文件。"""
        with tempfile.TemporaryDirectory() as tmp:
            vlm = Path(tmp) / "kb1" / "doc1" / "vlm"
            vlm.mkdir(parents=True)
            result = ingest_from_md(
                "kb1", "doc1",
                file_path=tmp,
                collection_name="coll",
                client=None,
            )
        assert result["success"] is False
        assert "无 .md 文件" in result["errors"][0]

    def test_collection_name_required(self):
        """collection_name 为空时返回错误。"""
        with tempfile.TemporaryDirectory() as tmp:
            vlm = Path(tmp) / "kb1" / "doc1" / "vlm"
            vlm.mkdir(parents=True)
            (vlm / "a.md").write_text("## 测试\n这是一段足够长的会议纪要内容用于解析", encoding="utf-8")
            result = ingest_from_md(
                "kb1", "doc1",
                file_path=tmp,
                collection_name="",
                client=None,
            )
        assert result["success"] is False
        assert "collection_name" in result["errors"][0]
