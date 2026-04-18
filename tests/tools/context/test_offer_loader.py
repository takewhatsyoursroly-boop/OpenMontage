"""Tests for tools.context.offer_loader."""
import os
import tempfile
from pathlib import Path

import pytest

from tools.context.offer_loader import OfferLoader


OFFER_FIXTURE = """---
slug: test-offer
name: Test Offer
price: $49
target: women 35-65 with energy issues
language: en
landing_url: https://example.com
---

## Primary angle
A calm, morning-focused promise.

## USPs
- Simple
- Fast
- Backed by research

## Proven hooks
- "The 3-second morning trick"
- "Why my 62-year-old aunt wakes up without coffee"

## Mechanism
Polyphenols bind to cortisol receptors.

## Banned claims
- "Cure"
- "Medical advice"
"""


@pytest.fixture
def offers_dir(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "test-offer.md").write_text(OFFER_FIXTURE)
        monkeypatch.setenv("OFFER_BRIEFS_DIR", d)
        yield d


def test_list_returns_all_slugs(offers_dir):
    loader = OfferLoader()
    result = loader.execute({"action": "list"})
    assert result.success
    assert result.data["slugs"] == ["test-offer"]


def test_load_returns_structured_dict(offers_dir):
    loader = OfferLoader()
    result = loader.execute({"action": "load", "slug": "test-offer"})
    assert result.success
    offer = result.data["offer"]
    assert offer["slug"] == "test-offer"
    assert offer["name"] == "Test Offer"
    assert offer["price"] == "$49"
    assert offer["target"] == "women 35-65 with energy issues"
    assert offer["landing_url"] == "https://example.com"
    assert "Primary angle" in offer["sections"]
    assert "calm, morning-focused" in offer["sections"]["Primary angle"]
    assert "USPs" in offer["sections"]
    assert "Banned claims" in offer["sections"]


def test_load_missing_slug_returns_error(offers_dir):
    loader = OfferLoader()
    result = loader.execute({"action": "load", "slug": "does-not-exist"})
    assert not result.success
    assert "does-not-exist" in result.error
    assert "test-offer" in result.error  # available slugs listed


def test_load_reads_multiple_sections(offers_dir):
    loader = OfferLoader()
    result = loader.execute({"action": "load", "slug": "test-offer"})
    assert result.success
    assert len(result.data["offer"]["sections"]) >= 4


def test_invalid_action_returns_error(offers_dir):
    loader = OfferLoader()
    result = loader.execute({"action": "invent-something"})
    assert not result.success
    assert "action" in result.error.lower()


def test_status_reports_unavailable_when_env_missing(monkeypatch):
    monkeypatch.delenv("OFFER_BRIEFS_DIR", raising=False)
    loader = OfferLoader()
    assert loader.get_status().value == "unavailable"


def test_status_reports_unavailable_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("OFFER_BRIEFS_DIR", str(tmp_path / "does-not-exist"))
    loader = OfferLoader()
    assert loader.get_status().value == "unavailable"


def test_status_reports_available_when_dir_exists(offers_dir):
    loader = OfferLoader()
    assert loader.get_status().value == "available"
