"""Offer brief loader — exposes synced offer markdown files as structured data.

Reads markdown files from OFFER_BRIEFS_DIR (a git-synced directory of offer
briefs) and returns structured dicts the agent can use as context for
proposal/script/asset stages.

File format:
    ---
    slug: akemi-detox-tea
    name: Akemi Detox Tea
    price: $49
    target: women 35-65 with fatigue
    language: en
    landing_url: https://...
    ---

    ## Primary angle
    ...

    ## USPs
    ...

Actions:
    - list  -> returns {"slugs": [...]}
    - load  -> returns {"offer": {slug, name, price, target, language,
                                   landing_url, sections: {heading: text}}}
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

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


class OfferLoader(BaseTool):
    name = "offer_loader"
    version = "0.1.0"
    tier = ToolTier.SOURCE
    capability = "offer_context"
    provider = "filesystem"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["env:OFFER_BRIEFS_DIR", "python:yaml"]
    install_instructions = (
        "Set OFFER_BRIEFS_DIR to a directory containing <slug>.md offer brief "
        "files with YAML frontmatter (see tools/context/offer_loader.py docstring)."
    )
    agent_skills: list[str] = []

    capabilities = ["list_offers", "load_offer"]

    best_for = [
        "loading direct-response offer context for ad/script stages",
        "providing banned-claims enforcement data",
        "surfacing proven hooks and mechanism framing",
    ]

    not_good_for = [
        "generic topic research (use research-director)",
        "dynamic or user-submitted offer briefs (fileystem-backed only)",
    ]

    input_schema = {
        "type": "object",
        "required": ["action"],
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "load"],
                "description": "'list' returns all offer slugs; 'load' fetches one by slug",
            },
            "slug": {
                "type": "string",
                "description": "Required when action is 'load'. Offer slug (filename without .md).",
            },
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "slugs": {"type": "array", "items": {"type": "string"}},
            "offer": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "name": {"type": "string"},
                    "price": {"type": "string"},
                    "target": {"type": "string"},
                    "language": {"type": "string"},
                    "landing_url": {"type": "string"},
                    "sections": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=64, vram_mb=0, disk_mb=1, network_required=False,
    )
    idempotency_key_fields = ["action", "slug"]
    side_effects: list[str] = []

    def _offers_dir(self) -> Path:
        raw = os.environ.get("OFFER_BRIEFS_DIR")
        if not raw:
            raise DependencyError(
                "OFFER_BRIEFS_DIR is not set. "
                "Point it at a directory of <slug>.md offer brief files."
            )
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            raise DependencyError(
                f"OFFER_BRIEFS_DIR does not resolve to a directory: {path}"
            )
        return path

    def check_dependencies(self) -> None:
        super().check_dependencies()
        self._offers_dir()

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        action = inputs.get("action")
        if action not in ("list", "load"):
            return ToolResult(
                success=False,
                error=f"Unknown action {action!r}. Expected 'list' or 'load'.",
            )

        try:
            offers_dir = self._offers_dir()
        except DependencyError as exc:
            return ToolResult(success=False, error=str(exc))

        if action == "list":
            slugs = sorted(p.stem for p in offers_dir.glob("*.md"))
            return ToolResult(success=True, data={"slugs": slugs})

        # action == "load"
        slug = inputs.get("slug")
        if not slug:
            return ToolResult(
                success=False, error="'slug' is required when action is 'load'."
            )

        path = offers_dir / f"{slug}.md"
        if not path.exists():
            available = sorted(p.stem for p in offers_dir.glob("*.md"))
            return ToolResult(
                success=False,
                error=(
                    f"Offer {slug!r} not found at {path}. "
                    f"Available slugs: {', '.join(available) or '(none)'}"
                ),
            )

        try:
            offer = self._parse_offer(slug, path.read_text())
        except Exception as exc:
            return ToolResult(
                success=False, error=f"Failed to parse {path}: {exc}"
            )

        return ToolResult(success=True, data={"offer": offer})

    @staticmethod
    def _parse_offer(slug: str, text: str) -> dict[str, Any]:
        frontmatter, body = OfferLoader._split_frontmatter(text)
        sections = OfferLoader._parse_sections(body)
        frontmatter.setdefault("slug", slug)
        frontmatter["sections"] = sections
        return frontmatter

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        """Split YAML frontmatter from markdown body."""
        if not text.startswith("---"):
            return {}, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text
        frontmatter = yaml.safe_load(parts[1]) or {}
        if not isinstance(frontmatter, dict):
            frontmatter = {}
        body = parts[2].lstrip("\n")
        return frontmatter, body

    @staticmethod
    def _parse_sections(body: str) -> dict[str, str]:
        """Split body at `## Heading` lines into a {heading: content} dict."""
        sections: dict[str, str] = {}
        current: str | None = None
        buffer: list[str] = []

        for line in body.splitlines():
            match = re.match(r"^##\s+(.+?)\s*$", line)
            if match:
                if current is not None:
                    sections[current] = "\n".join(buffer).strip()
                current = match.group(1).strip()
                buffer = []
            else:
                buffer.append(line)

        if current is not None:
            sections[current] = "\n".join(buffer).strip()

        return sections
