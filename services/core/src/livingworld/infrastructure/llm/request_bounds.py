"""Provider-specific conservative request bounds through audited upstream framing."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

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
        for model, gateway in gateways.items():
            configured = configuration.models[model]
            provider = configuration.providers[model.provider_id].config
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

    def supports_request_bound(self, model) -> bool:
        return model in self._profiles and self._helper.is_file()

    def bound(self, request):
        fallback = self._fallback.bound(request)
        if fallback is None or not self.supports_request_bound(request.model):
            return fallback
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
