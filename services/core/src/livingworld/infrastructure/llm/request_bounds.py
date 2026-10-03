"""Provider-specific conservative request bounds through audited upstream framing."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from time import monotonic

from livingworld.application.llm import AdapterKind, LLMContractError, LLMError
from livingworld.application.llm_budget import UsageUpperBound

_PRESETS = json.loads(Path(__file__).with_name("model_presets.json").read_text(encoding="utf-8"))[
    "models"
]
_HELPER_NAME = "dreamtalk-deepseek-request-bound" + (".exe" if os.name == "nt" else "")


def _helper_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "request-bound" / _HELPER_NAME
    return (
        Path(__file__).resolve().parents[6]
        / "tools/deepseek-request-bound/target/release"
        / _HELPER_NAME
    )


class ProviderRequestUsageBounder:
    """Reuse model-wide bounds for unsupported providers; never promote estimates."""

    def __init__(self, configuration, gateways):
        self._fallback = configuration.registry.usage_bounder()
        self._helper = _helper_path()
        self._profiles = {}
        self._cache: dict[bytes, int] = {}
        self._count_gateways = {}
        self._counts: dict[bytes, tuple[float, int | None]] = {}
        for model, gateway in gateways.items():
            configured = configuration.models[model]
            provider = configuration.providers[model.provider_id].config
            if configured.adapter_kind is AdapterKind.OPENAI_RESPONSES and getattr(
                gateway, "supports_input_count", False
            ):
                self._count_gateways[model] = gateway
                continue
            if (
                configured.adapter_kind is not AdapterKind.OPENAI_COMPATIBLE
                or provider.endpoint is None
            ):
                continue
            # Exact verified service/model pairs only: a proxy with the same model
            # name does not inherit the official service's framing guarantees.
            base = provider.endpoint.base_url.rstrip("/")
            preset = next(
                (
                    item
                    for item in _PRESETS
                    if item["model_id"] == model.model_id
                    and base in item["base_urls"]
                    and item["bound_encoding"]
                ),
                None,
            )
            if preset is not None:
                self._profiles[model] = (preset["bound_encoding"], gateway)

    def packing_feedback(self, request):
        """Raw trustworthy count and configured input ceiling, solely for packing."""
        fallback = self._fallback.bound(request)
        if fallback is None:
            return None
        if request.model in self._count_gateways:
            prepared = self._count_payload(request)
            cached = self._counts.get(prepared[2]) if prepared is not None else None
            if cached is not None and cached[0] > monotonic() and cached[1] is not None:
                return cached[1], fallback.input_tokens
            return None
        profile = self._profiles.get(request.model)
        if profile is None:
            return None
        try:
            encoding, gateway = profile
            payload = gateway.token_reservation_payload(request)
            data = json.dumps(
                {"encoding": encoding, "payload": payload},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            count = self._cache.get(hashlib.sha256(data).digest())
            return (count, fallback.input_tokens) if count is not None else None
        except (ValueError, TypeError, LLMContractError, LLMError):
            return None

    def supports_request_bound(self, model) -> bool:
        return model in self._count_gateways or (model in self._profiles and self._helper.is_file())

    def _count_payload(self, request):
        gateway = self._count_gateways.get(request.model)
        if gateway is None:
            return None
        try:
            payload = gateway.token_reservation_payload(request)
            if payload is None:
                return None
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(data) > 4 * 1024 * 1024:
                return None
            return gateway, payload, hashlib.sha256(data).digest()
        except (ValueError, TypeError, LLMContractError, LLMError):
            return None

    async def prepare(self, request) -> None:
        """Count outside accounting transactions; sync bound() reads facts only."""
        if self._fallback.bound(request) is None:
            return
        prepared = self._count_payload(request)
        if prepared is None:
            return
        gateway, payload, key = prepared
        cached = self._counts.get(key)
        if cached is not None and cached[0] > monotonic():
            return
        try:
            async with asyncio.timeout(5):
                count = await gateway.count_input_tokens(request, payload)
        except (TimeoutError, OSError, ValueError, LLMContractError, LLMError):
            count = None
        if type(count) is not int or not 0 <= count <= 2**63 - 1:
            count = None
        if len(self._counts) >= 64:
            self._counts.clear()
        # Include failures briefly to avoid repeating count requests when output
        # is clipped or the same physical request proceeds to its budget guard.
        self._counts[key] = (monotonic() + 30, count)

    def bound(self, request):
        fallback = self._fallback.bound(request)
        if fallback is None or not self.supports_request_bound(request.model):
            return fallback
        if request.model in self._count_gateways:
            prepared = self._count_payload(request)
            cached = self._counts.get(prepared[2]) if prepared is not None else None
            if cached is None or cached[0] <= monotonic() or cached[1] is None:
                return fallback
            return UsageUpperBound(min(fallback.input_tokens, cached[1]), fallback.output_tokens)
        encoding, gateway = self._profiles[request.model]
        try:
            payload = gateway.token_reservation_payload(request)
            if payload is None:
                return fallback
            data = json.dumps(
                {"encoding": encoding, "payload": payload},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(data) > 4 * 1024 * 1024:
                return fallback
            key = hashlib.sha256(data).digest()
            upper = self._cache.get(key)
            if upper is None:
                result = subprocess.run(
                    [str(self._helper)],
                    input=data,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                if result.returncode or len(result.stdout) > 256:
                    return fallback
                upper = json.loads(result.stdout)["input_upper_bound"]
                if type(upper) is not int or upper < 0:
                    return fallback
                # Retain only digests and numeric bounds, never prompts or keys.
                if len(self._cache) >= 64:
                    self._cache.clear()
                self._cache[key] = upper
            return UsageUpperBound(min(fallback.input_tokens, upper), fallback.output_tokens)
        except (
            OSError,
            subprocess.TimeoutExpired,
            ValueError,
            KeyError,
            TypeError,
            LLMContractError,
            LLMError,
        ):
            return fallback
