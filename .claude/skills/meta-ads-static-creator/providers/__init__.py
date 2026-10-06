"""Image-generation providers for generate-blank-ad.py.

Each provider module exposes the same small interface:

    NAME: str
    ENV_KEY: str
    DEFAULT_MODEL: str
    plan(req) -> Plan              # payload preview + cost estimate; no network
    generate(req, plan, resume_id=None) -> PlateResult

There is no silent cross-provider fallback: switching would spend on a
different bill at a different price without approval.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROVIDERS = ("fal", "replicate")
ENV_KEYS = {"fal": "FAL_KEY", "replicate": "REPLICATE_API_TOKEN"}
QUALITIES = ("low", "medium", "high")
DEFAULT_QUALITY = "low"
DEFAULT_PROVIDER = "replicate"


class ProviderError(RuntimeError):
    """A provider failure with a user-facing message.

    `billed` is the provider's documented billing outcome when known
    (True/False) or None when unknown.
    """

    def __init__(
        self,
        message: str,
        billed: Optional[bool] = None,
        prediction_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.billed = billed
        self.prediction_id = prediction_id


@dataclass
class PlateRequest:
    prompt: str
    no_text_suffix: str
    ratio: str
    images: List[Path]
    label: str
    out_dir: Path
    quality: str = DEFAULT_QUALITY
    model: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    provider: str
    model: str
    payload_preview: Dict[str, Any]
    calls: int
    est_cost_usd: Optional[float]
    cost_note: str
    crop_to: Optional[Tuple[int, int]] = None
    prompt_sent: str = ""


@dataclass
class PlateResult:
    data: bytes
    provider: str
    model: str
    meta: Dict[str, Any] = field(default_factory=dict)


def resolve_provider(cli: Optional[str], spec: Dict[str, Any]) -> Tuple[str, str]:
    """Pick the provider. Returns (provider, reason).

    Order: --provider > spec.json "provider" > IMAGE_PROVIDER env >
    whichever single credential is present > replicate (both keys set,
    or neither). Users with only FAL_KEY still use fal.
    """
    for source, value in (
        ("--provider", cli),
        ("spec.json provider", spec.get("provider")),
        ("IMAGE_PROVIDER", os.environ.get("IMAGE_PROVIDER")),
    ):
        if not value:
            continue
        value = value.strip().lower()
        if not value:
            continue
        if value not in PROVIDERS:
            raise SystemExit(
                f"Error: unknown provider '{value}' from {source}; "
                f"use one of {', '.join(PROVIDERS)}."
            )
        return value, source
    have = [p for p in PROVIDERS if os.environ.get(ENV_KEYS[p])]
    if len(have) == 1:
        return have[0], f"only {ENV_KEYS[have[0]]} is set"
    if len(have) == 2:
        return (
            DEFAULT_PROVIDER,
            "both keys set; defaulting to replicate (set IMAGE_PROVIDER to choose)",
        )
    return DEFAULT_PROVIDER, "no key set"


def resolve_quality(
    cli_quality: Optional[str] = None,
    final: bool = False,
    spec_quality: Optional[str] = None,
) -> str:
    """Pick quality. Returns low, medium, or high.

    Order: --quality > --final (high) > spec.json quality / provider_options
    quality > low. First-pass plates and edits stay low unless the user asks
    for a final/high render.
    """
    for source, value in (
        ("--quality", cli_quality),
        ("--final", "high" if final else None),
        ("spec.json quality", spec_quality),
    ):
        if not value:
            continue
        value = str(value).strip().lower()
        if not value:
            continue
        if value not in QUALITIES:
            raise SystemExit(
                f"Error: quality must be one of {', '.join(QUALITIES)}; "
                f"got '{value}' from {source}."
            )
        return value
    return DEFAULT_QUALITY


def billed_label(billed: Optional[bool]) -> str:
    if billed is True:
        return "billed"
    if billed is False:
        return "not billed per provider docs"
    return "billing unknown"


def load_provider(name: str):
    if name == "fal":
        from . import fal_provider as mod
    elif name == "replicate":
        from . import replicate_provider as mod
    else:  # pragma: no cover - guarded by resolve_provider
        raise SystemExit(f"Error: unknown provider '{name}'")
    return mod
