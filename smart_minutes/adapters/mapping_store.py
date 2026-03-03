"""IMappingStore 实现（当前内存 stub，可改为 DB/配置）。"""
from typing import Dict, List, Optional



class MappingStoreAdapter:
    """实现 IMappingStore，可从 DB 或配置加载。"""

    def __init__(self, db_uri: Optional[str] = None, initial_oral_map: Optional[dict] = None):
        self._db_uri = db_uri
        self._oral_to_formal = dict(initial_oral_map or {})  # 口头→正式人名
        self._meeting_terms: dict = {}  # (会议类型, 会议名) → 专业词列表

    def resolve_oral_to_formal(self, oral_name: str) -> Optional[str]:
        """口头称呼 → 正式人名。"""
        return self._oral_to_formal.get(oral_name.strip())

    def resolve_oral_to_formal_candidates(self, oral_name: str) -> List[str]:
        """口头称呼 → 所有正式人名候选。"""
        v = self._oral_to_formal.get(oral_name.strip())
        return [v] if v else []

    def batch_add_or_update_oral_name_mappings(
        self,
        mappings: List[Dict],
    ) -> Dict[str, int]:
        """批量添加或更新口头称呼映射（内存 stub 实现）。"""
        success_count = 0
        failed_count = 0
        for m in mappings:
            oral = (m.get("oral_name") or "").strip()
            formal = (m.get("formal_name") or "").strip()
            if not oral or not formal:
                failed_count += 1
                continue
            self._oral_to_formal[oral] = formal
            success_count += 1
        return {"success_count": success_count, "failed_count": failed_count}

    def get_professional_terms(self, meeting_type: str, meeting_name: str) -> List[str]:
        """会议类型/名称 → 专业名词列表。"""
        key = (meeting_type or "", meeting_name or "")
        return list(self._meeting_terms.get(key, []))
