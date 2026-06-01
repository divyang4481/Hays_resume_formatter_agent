from __future__ import annotations

import logging
import os
import boto3
from botocore.exceptions import ProfileNotFound

from src.shared.config import settings

logger = logging.getLogger(__name__)


def get_boto3_session() -> boto3.Session:
    """
    Get a boto3 Session.
    - If running in AWS ECS (detected via ECS task role environment variables),
      uses the default session to leverage the Task IAM Role.
    - Otherwise, attempts to use the AWS_PROFILE configured in settings.
    - Falls back gracefully to the default session if the profile is not found or fails to load.
    """
    profile = (settings.aws_profile or "").strip()

    # ECS Task IAM credentials check
    is_ecs = any(
        var in os.environ
        for var in [
            "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
            "AWS_CONTAINER_CREDENTIALS_FULL_URI",
            "AWS_EXECUTION_ENV",
        ]
    )

    if is_ecs:
        logger.info("AWS ECS environment detected. Using default Session (Task IAM Role).")
        return boto3.Session()

    if profile:
        try:
            session = boto3.Session(profile_name=profile)
            # Access credentials to verify they are loadable
            session.get_credentials()
            logger.info("Using configured AWS profile: %s", profile)
            return session
        except ProfileNotFound:
            logger.warning("AWS Profile '%s' not found. Falling back to default Session.", profile)
        except Exception as e:
            logger.warning(
                "Failed to initialize Session with profile '%s' (%s). Falling back to default Session.",
                profile,
                e,
            )

    logger.info("Using default AWS Session.")
    return boto3.Session()
