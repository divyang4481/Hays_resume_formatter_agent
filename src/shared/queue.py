from __future__ import annotations

import json
from queue import Empty, Queue
from typing import Any

import boto3

from src.shared.config import settings


class InMemoryQueueBus:
    def __init__(self) -> None:
        self.template_analysis_queue: Queue[dict[str, Any]] = Queue()
        self.resume_format_queue: Queue[dict[str, Any]] = Queue()

    def push_template_analysis(self, payload: dict[str, Any]) -> None:
        self.template_analysis_queue.put(payload)

    def push_resume_format(self, payload: dict[str, Any]) -> None:
        self.resume_format_queue.put(payload)

    def pop_template_analysis(self, timeout_seconds: float = 1.0) -> dict[str, Any] | None:
        try:
            return self.template_analysis_queue.get(timeout=timeout_seconds)
        except Empty:
            return None

    def pop_resume_format(self, timeout_seconds: float = 1.0) -> dict[str, Any] | None:
        try:
            return self.resume_format_queue.get(timeout=timeout_seconds)
        except Empty:
            return None


class SQSQueueBus:
    def __init__(self) -> None:
        self.recreate_client()

    def recreate_client(self) -> None:
        self.client = boto3.client("sqs", region_name=settings.aws_region)
        self.template_analysis_url = settings.sqs_template_analysis_queue_url
        self.resume_format_url = settings.sqs_resume_format_queue_url

    def push_template_analysis(self, payload: dict[str, Any]) -> None:
        self.client.send_message(
            QueueUrl=self.template_analysis_url,
            MessageBody=json.dumps(payload, ensure_ascii=True),
        )

    def push_resume_format(self, payload: dict[str, Any]) -> None:
        self.client.send_message(
            QueueUrl=self.resume_format_url,
            MessageBody=json.dumps(payload, ensure_ascii=True),
        )

    def _receive_one(self, queue_url: str, timeout_seconds: float = 1.0) -> dict[str, Any] | None:
        wait_time = max(0, min(int(timeout_seconds), settings.sqs_wait_time_seconds))
        response = self.client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait_time,
            VisibilityTimeout=settings.sqs_visibility_timeout_seconds,
        )
        messages = response.get("Messages", [])
        if not messages:
            return None

        message = messages[0]
        body = json.loads(message["Body"])

        # Demo simplification: acknowledge immediately. Move this after successful processing for strict at-least-once behavior.
        self.client.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
        return body

    def pop_template_analysis(self, timeout_seconds: float = 1.0) -> dict[str, Any] | None:
        return self._receive_one(self.template_analysis_url, timeout_seconds)

    def pop_resume_format(self, timeout_seconds: float = 1.0) -> dict[str, Any] | None:
        return self._receive_one(self.resume_format_url, timeout_seconds)


queue_bus = SQSQueueBus() if settings.use_aws_services else InMemoryQueueBus()
