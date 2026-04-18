"""Cloudflare R2 upload publisher for OpenMontage artifacts.

Uploads local files (final video, SRT, script JSON, decision log) to a
Cloudflare R2 bucket and returns public URLs. Shares a bucket with MVMT
Printer so renders can be surfaced in the Create FB Campaigns wizard.

Actions:
    - upload -> uploads local_path to s3 key, returns {public_url}
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import boto3

from tools.base_tool import (
    BaseTool,
    DependencyError,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)


REQUIRED_ENV = (
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT_URL",
    "R2_PUBLIC_URL",
)


class R2Storage(BaseTool):
    name = "r2_storage"
    version = "0.1.0"
    tier = ToolTier.PUBLISH
    capability = "artifact_storage"
    provider = "cloudflare-r2"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.API

    dependencies = [
        "env:R2_BUCKET",
        "env:R2_ACCESS_KEY_ID",
        "env:R2_SECRET_ACCESS_KEY",
        "env:R2_ENDPOINT_URL",
        "env:R2_PUBLIC_URL",
        "python:boto3",
    ]
    install_instructions = (
        "Set all R2_* env vars (R2_BUCKET, R2_ACCESS_KEY_ID, "
        "R2_SECRET_ACCESS_KEY, R2_ENDPOINT_URL, R2_PUBLIC_URL) and "
        "install boto3."
    )
    agent_skills: list[str] = []

    capabilities = ["upload_artifact"]

    best_for = [
        "publishing final videos and artifacts for downstream consumers",
        "sharing render output with the MVMT Printer wizard",
        "cheap long-lived storage without S3 egress fees",
    ]
    not_good_for = [
        "streaming delivery (R2 is object storage, not CDN-front)",
        "private artifacts (this tool uploads to public-URL bucket)",
    ]

    input_schema = {
        "type": "object",
        "required": ["action"],
        "properties": {
            "action": {"type": "string", "enum": ["upload"]},
            "local_path": {"type": "string"},
            "key": {
                "type": "string",
                "description": "S3/R2 object key under the bucket (e.g. openmontage/<run-id>/final.mp4)",
            },
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "public_url": {"type": "string"},
            "bucket": {"type": "string"},
            "key": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=10, network_required=True,
    )
    idempotency_key_fields = ["key"]
    side_effects = ["writes_to_cloudflare_r2"]

    def _client(self):
        missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
        if missing:
            raise DependencyError(
                f"Missing R2 env vars: {', '.join(missing)}. "
                f"{self.install_instructions}"
            )
        return boto3.client(
            "s3",
            endpoint_url=os.environ["R2_ENDPOINT_URL"],
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )

    def check_dependencies(self) -> None:
        super().check_dependencies()
        # Validate env vars are actually set (super only checks env: deps above,
        # but we also want to short-circuit before boto3 instantiation)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        action = inputs.get("action")
        if action != "upload":
            return ToolResult(
                success=False,
                error=f"Unknown action {action!r}. Expected 'upload'.",
            )

        local_path = inputs.get("local_path")
        key = inputs.get("key")
        if not local_path or not key:
            return ToolResult(
                success=False,
                error="'local_path' and 'key' are required for upload.",
            )

        if not Path(local_path).exists():
            return ToolResult(
                success=False, error=f"Local file not found: {local_path}",
            )

        try:
            client = self._client()
        except DependencyError as exc:
            return ToolResult(success=False, error=str(exc))

        bucket = os.environ["R2_BUCKET"]
        public_base = os.environ["R2_PUBLIC_URL"].rstrip("/")

        try:
            client.upload_file(local_path, bucket, key)
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"R2 upload failed for {key}: {exc}",
            )

        return ToolResult(
            success=True,
            data={
                "public_url": f"{public_base}/{key}",
                "bucket": bucket,
                "key": key,
            },
            artifacts=[local_path],
        )
