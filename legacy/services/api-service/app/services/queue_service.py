"""Queue service for RabbitMQ integration.

This module provides the interface for publishing jobs to RabbitMQ
and consuming results. The actual ML processing is handled by
the separate ML service.

Message Contract:
-----------------
Job Message (API -> ML Service):
{
    "job_id": "uuid",
    "project_id": "uuid",
    "job_type": "account_matching" | "type_mapping" | "export",
    "input_data": {
        "source_data": [...],
        "target_data": [...],
        "options": {...}
    },
    "created_at": "ISO timestamp"
}

Result Message (ML Service -> API):
{
    "job_id": "uuid",
    "status": "completed" | "failed",
    "progress": 100.0,
    "result_data": {
        "grouped_mappings": [...],
        "total_accounts": int,
        "total_types": int
    },
    "error_message": null | "error description",
    "completed_at": "ISO timestamp"
}
"""
import json
import logging
from typing import Dict, Any, Optional, Callable
from app.core.config import settings

logger = logging.getLogger(__name__)


class QueueService:
    """Service for RabbitMQ message queue operations.
    
    This is a stub implementation that will be connected to
    RabbitMQ when the ML service is deployed separately.
    For now, it provides the interface and logs operations.
    """
    
    def __init__(self):
        self._connection = None
        self._channel = None
        self._is_connected = False
    
    async def connect(self) -> bool:
        """Connect to RabbitMQ.
        
        Returns True if connected, False if queue is unavailable.
        The application should work in degraded mode without the queue.
        """
        try:
            # TODO: Implement actual RabbitMQ connection using aio-pika
            # For now, this is a stub that always returns False
            # indicating queue is not available
            logger.info(f"Queue connection attempted to: {settings.RABBITMQ_URL}")
            logger.warning("RabbitMQ not configured - running in synchronous mode")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from RabbitMQ."""
        if self._connection:
            # await self._connection.close()
            self._connection = None
            self._channel = None
            self._is_connected = False
    
    async def publish_job(self, message: Dict[str, Any]) -> bool:
        """Publish a job message to the matching queue.
        
        Args:
            message: Job message following the contract above
            
        Returns:
            True if published successfully, False otherwise
        """
        if not self._is_connected:
            logger.debug(f"Queue not connected - job not queued: {message.get('job_id')}")
            return False
        
        try:
            # TODO: Implement actual message publishing
            # await self._channel.default_exchange.publish(
            #     aio_pika.Message(
            #         body=json.dumps(message).encode(),
            #         content_type="application/json"
            #     ),
            #     routing_key=settings.QUEUE_MATCHING_JOBS
            # )
            logger.info(f"Job published to queue: {message.get('job_id')}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish job: {e}")
            return False
    
    async def consume_results(
        self,
        callback: Callable[[Dict[str, Any]], None]
    ):
        """Start consuming result messages from the results queue.
        
        This is used by the API service to receive completion notifications.
        
        Args:
            callback: Function to call with each result message
        """
        if not self._is_connected:
            logger.warning("Queue not connected - cannot consume results")
            return
        
        try:
            # TODO: Implement actual message consumption
            # queue = await self._channel.declare_queue(
            #     settings.QUEUE_MATCHING_RESULTS,
            #     durable=True
            # )
            # async for message in queue:
            #     data = json.loads(message.body.decode())
            #     await callback(data)
            #     await message.ack()
            pass
        except Exception as e:
            logger.error(f"Error consuming results: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if queue service is available."""
        return self._is_connected


# Message contract definitions for documentation
JOB_MESSAGE_SCHEMA = {
    "type": "object",
    "required": ["job_id", "project_id", "job_type"],
    "properties": {
        "job_id": {"type": "string", "format": "uuid"},
        "project_id": {"type": "string", "format": "uuid"},
        "job_type": {
            "type": "string",
            "enum": ["account_matching", "type_mapping", "export"]
        },
        "input_data": {
            "type": "object",
            "properties": {
                "source_data": {"type": "array"},
                "target_data": {"type": "array"},
                "options": {"type": "object"}
            }
        },
        "created_at": {"type": "string", "format": "date-time"}
    }
}

RESULT_MESSAGE_SCHEMA = {
    "type": "object",
    "required": ["job_id", "status"],
    "properties": {
        "job_id": {"type": "string", "format": "uuid"},
        "status": {
            "type": "string",
            "enum": ["completed", "failed"]
        },
        "progress": {"type": "number", "minimum": 0, "maximum": 100},
        "result_data": {"type": "object"},
        "error_message": {"type": ["string", "null"]},
        "completed_at": {"type": "string", "format": "date-time"}
    }
}


# Singleton instance
queue_service = QueueService()
