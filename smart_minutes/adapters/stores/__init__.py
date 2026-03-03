"""
存储适配器：提供各种持久化存储的实现
"""
from smart_minutes.adapters.stores.mapping_mysql import MappingStoreMySQL
from smart_minutes.adapters.stores.mapping_redis import MappingStoreRedis
from smart_minutes.adapters.stores.attachment_metadata import AttachmentMetadataStore
from smart_minutes.adapters.stores.template_store import TemplateStore
from smart_minutes.adapters.stores.proper_noun_store import ProperNounStore

__all__ = [
    "MappingStoreMySQL",
    "MappingStoreRedis",
    "AttachmentMetadataStore",
    "TemplateStore",
    "ProperNounStore",
]
