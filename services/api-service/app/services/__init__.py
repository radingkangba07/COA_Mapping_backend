"""Services module - lazy imports to avoid pulling in all dependencies."""


def __getattr__(name):
    """Lazy import services on first access."""
    if name in ("ERPService", "erp_service"):
        from app.services.erp_service import ERPService, erp_service
        return ERPService if name == "ERPService" else erp_service
    if name in ("MatchingService", "matching_service"):
        from app.services.matching_service import MatchingService, matching_service
        return MatchingService if name == "MatchingService" else matching_service
    if name == "JobService":
        from app.services.job_service import JobService
        return JobService
    if name in ("QueueService", "queue_service"):
        from app.services.queue_service import QueueService, queue_service
        return QueueService if name == "QueueService" else queue_service
    if name in ("StorageService", "storage_service", "get_content_type"):
        from app.services.storage_service import StorageService, storage_service, get_content_type
        if name == "StorageService":
            return StorageService
        return storage_service if name == "storage_service" else get_content_type
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ERPService", "erp_service",
    "MatchingService", "matching_service",
    "JobService",
    "QueueService", "queue_service",
    "StorageService", "storage_service", "get_content_type"
]