"""IndexTTS 2.5 transports. Generation is submitted once, with no route fallback."""

import asyncio
import base64
import hashlib
import json
import re
from urllib.parse import quote, urlsplit
from uuid import uuid5

import httpx

from livingworld.application.llm_config import SecretRef
from livingworld.application.speech_contracts import MAX_AUDIO_BYTES, SpeechError

HF_BASE = "https://indexteam-indextts-2-5-demo.hf.space"
CLOUD_BASE = "https://cp.compshare.cn"


async def json_response(response, *, job_status=False):
    if not response.is_success:
        raise SpeechError("speech_provider_rejected")
    if len(response.content) > 2 * 1024 * 1024:
        raise SpeechError("speech_provider_protocol")
    try:
        result = response.json()
    except ValueError:
        raise SpeechError("speech_provider_protocol") from None
    if isinstance(result, dict) and (
        result.get("RetCode", 0) != 0 or not job_status and result.get("error") is not None
    ):
        raise SpeechError("speech_provider_rejected")
    return result


def cloud_asset_url(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or not any(
            host == suffix or host.endswith("." + suffix)
            for suffix in (
                "ufileos.com",
                "ucloud.cn",
                "ucloud.com.cn",
                "compshare.cn",
            )
        )
    ):
        raise SpeechError("speech_asset_host_untrusted")
    return url


async def download(client, url):
    data = bytearray()
    async with client.stream("GET", url) as response:
        if not response.is_success:
            raise SpeechError("speech_audio_download_failed")
        async for chunk in response.aiter_bytes():
            if len(data) + len(chunk) > MAX_AUDIO_BYTES:
                raise SpeechError("voice_audio_size_limit")
            data.extend(chunk)
    return bytes(data)


class IndexSpeechProviders:
    def __init__(self, credentials, voice_cache):
        self.credentials = credentials
        self.voice_cache = voice_cache

    async def _secret(self, settings):
        if settings.secret_ref is None:
            return None
        secret = await self.credentials.resolve(SecretRef(settings.secret_ref))
        return secret.reveal_for_adapter()

    async def synthesize(self, settings, card, manifest, text, identity, save_remote, progress):
        try:
            return await self._synthesize(
                settings, card, manifest, text, identity, save_remote, progress
            )
        except httpx.HTTPError:
            # A transport failure cannot establish whether the submitted job ran.
            raise SpeechError("speech_status_lost") from None

    async def _synthesize(self, settings, card, manifest, text, identity, save_remote, progress):
        secret = await self._secret(settings)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(900, connect=15), follow_redirects=False, trust_env=False
        ) as client:
            if settings.provider == "local":
                headers = {"Authorization": f"Bearer {secret}"} if secret else {}
                try:
                    health = await client.get(
                        settings.local_url + "/health", headers=headers, timeout=10
                    )
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    raise SpeechError("speech_local_unavailable") from None
                if health.status_code == 401:
                    raise SpeechError("speech_local_key_required")
                if health.status_code == 404:
                    raise SpeechError("speech_local_bridge_outdated")
                info = await json_response(health)
                if info.get("protocol") != 2 or info.get("engine") != "indextts-2.5":
                    raise SpeechError("speech_provider_protocol")
                if info.get("inference_revision") != 8:
                    raise SpeechError("speech_local_bridge_outdated")
                created = await client.post(
                    settings.local_url + "/jobs",
                    headers=headers,
                    json={
                        "engine": "indextts-2.5",
                        "text": text,
                        "language": manifest["language"],
                        "speed": manifest["speed"],
                        "reference_name": manifest["reference"],
                        "reference_base64": base64.b64encode(card.audio).decode("ascii"),
                        "request_id": str(identity),
                    },
                )
                if created.status_code == 409:
                    raise SpeechError("speech_busy")
                await json_response(created)
                await save_remote(str(identity))
                for _ in range(900):
                    response = await client.get(
                        settings.local_url + "/jobs/" + str(identity),
                        headers=headers,
                        timeout=10,
                    )
                    if not response.is_success:
                        raise SpeechError("speech_status_lost")
                    result = await json_response(response, job_status=True)
                    state = result.get("state")
                    if state == "ready":
                        progress("downloading_audio")
                        data = bytearray()
                        async with client.stream(
                            "GET",
                            settings.local_url + "/jobs/" + str(identity) + "/audio",
                            headers=headers,
                        ) as response:
                            if not response.is_success:
                                raise SpeechError("speech_audio_download_failed")
                            async for chunk in response.aiter_bytes():
                                if len(data) + len(chunk) > MAX_AUDIO_BYTES:
                                    raise SpeechError("voice_audio_size_limit")
                                data.extend(chunk)
                        return bytes(data)
                    if state == "failed":
                        if result.get("error") in {
                            "speech_audio_incomplete",
                            "speech_sentence_capacity",
                            "speech_outcome_unknown",
                        }:
                            raise SpeechError(result["error"])
                        raise SpeechError("speech_generation_failed")
                    if state == "expired":
                        raise SpeechError("speech_cache_expired")
                    if state != "running":
                        raise SpeechError("speech_provider_protocol")
                    phase = result.get("phase")
                    if phase not in {
                        "accepted",
                        "loading_model",
                        "preparing_text",
                        "synthesizing",
                        "saving_audio",
                    }:
                        raise SpeechError("speech_provider_protocol")
                    segment, segments = result.get("segment"), result.get("segments")
                    if segment is not None and (
                        type(segment) is not int
                        or type(segments) is not int
                        or not 1 <= segment <= segments <= 2000
                    ):
                        raise SpeechError("speech_provider_protocol")
                    progress(phase, segment, segments)
                    await asyncio.sleep(1)
                raise SpeechError("speech_status_lost")
            if settings.provider == "huggingface":
                progress("waiting_remote")
                return await self._huggingface(client, secret, card, manifest, text, save_remote)
            if not secret:
                raise SpeechError("speech_key_required")
            progress("waiting_remote")
            return await self._cloud(
                client, secret, settings, card, manifest, text, identity, save_remote
            )

    async def pricing(self, settings):
        secret = await self._secret(settings)
        if not secret:
            raise SpeechError("speech_key_required")
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
            return await json_response(
                await client.get(
                    CLOUD_BASE + "/audio/v1/pricing", headers={"Authorization": f"Bearer {secret}"}
                )
            )

    async def _huggingface(self, client, secret, card, manifest, text, save_remote):
        headers = {"Authorization": f"Bearer {secret}"} if secret else {}
        if secret:
            account = await json_response(
                await client.get("https://huggingface.co/api/whoami-v2", headers=headers)
            )
            # ZeroGPU PRO accounts can spend credits after quota exhaustion. The free
            # route never sends their token; unknown account tiers also fail closed.
            if account.get("type") != "user" or account.get("isPro") is not False:
                raise SpeechError("speech_hf_free_account_required")
        config = await json_response(await client.get(HF_BASE + "/config", headers=headers))
        components = {item["id"]: item for item in config.get("components", [])}
        endpoints = [
            item for item in config.get("dependencies", []) if item.get("api_name") == "gen_single"
        ]
        if len(endpoints) != 1 or len(endpoints[0].get("inputs", [])) != 26:
            raise SpeechError("speech_hf_api_changed")
        inputs = [components.get(identity, {}) for identity in endpoints[0]["inputs"]]
        if [item.get("type") for item in inputs[:4]] != ["radio", "audio", "textbox", "dropdown"]:
            raise SpeechError("speech_hf_api_changed")
        values = [item.get("props", {}).get("value") for item in inputs]
        choices = inputs[0].get("props", {}).get("choices", [])
        if not choices:
            raise SpeechError("speech_hf_api_changed")
        # gr.Radio(type=index) still receives a choice value on the wire.
        values[0] = choices[0][1] if isinstance(choices[0], list) else choices[0]
        uploaded = await json_response(
            await client.post(
                HF_BASE + "/gradio_api/upload",
                headers=headers,
                files={
                    "files": (
                        manifest["reference"],
                        card.audio,
                        "audio/wav" if manifest["reference"].endswith("wav") else "audio/mpeg",
                    )
                },
            )
        )
        if not isinstance(uploaded, list) or len(uploaded) != 1 or not isinstance(uploaded[0], str):
            raise SpeechError("speech_provider_protocol")
        values[1] = {"path": uploaded[0], "meta": {"_type": "gradio.FileData"}}
        values[2], values[3], values[4], values[14], values[15] = (
            text,
            manifest["language"],
            None,
            "",
            False,
        )
        values[17] = 1 / manifest["speed"]
        response = await json_response(
            await client.post(
                HF_BASE + "/gradio_api/call/gen_single", headers=headers, json={"data": values}
            )
        )
        event_id = response.get("event_id")
        if not isinstance(event_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", event_id):
            raise SpeechError("speech_provider_protocol")
        await save_remote(event_id)
        event, received = "", 0
        async with client.stream(
            "GET", HF_BASE + "/gradio_api/call/gen_single/" + event_id, headers=headers
        ) as response:
            if not response.is_success:
                raise SpeechError("speech_provider_rejected")
            async for line in response.aiter_lines():
                received += len(line)
                if received > 2 * 1024 * 1024:
                    raise SpeechError("speech_provider_protocol")
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    if event == "error":
                        raise SpeechError("speech_hf_quota_or_generation")
                    if event == "complete":
                        output = json.loads(line[5:])
                        value = output[0]
                        file = value.get("value", value)
                        path = file.get("path") if isinstance(file, dict) else None
                        if not isinstance(path, str) or len(path) > 4096:
                            raise SpeechError("speech_provider_protocol")
                        return await download(
                            client, HF_BASE + "/gradio_api/file=" + quote(path, safe="/")
                        )
        raise SpeechError("speech_outcome_unknown")

    async def _cloud(self, client, secret, settings, card, manifest, text, identity, save_remote):
        headers = {"Authorization": f"Bearer {secret}"}
        pricing = await json_response(
            await client.get(CLOUD_BASE + "/audio/v1/pricing", headers=headers)
        )
        unit, rate = pricing.get("unit_characters"), pricing.get("costs", {}).get("text_to_speech")
        if pricing.get("enabled") is not True or unit != 10 or type(rate) is not int or rate < 0:
            raise SpeechError("speech_price_unavailable")
        cost = (sum(c.isalpha() or c.isdecimal() for c in text) * rate + unit - 1) // unit
        if pricing.get("balance", {}).get("available_points", -1) < cost:
            raise SpeechError("speech_balance_insufficient")
        key = hashlib.sha256(f"{settings.secret_ref}:{card.digest}".encode()).hexdigest()
        voice = await self.voice_cache.remote_voice(card.world_id, key)
        if voice is None:
            voice = await self._cloud_voice(client, headers, card, manifest, key)
            await self.voice_cache.save_remote_voice(card.world_id, key, voice)
        body = {
            "text": text,
            "language": manifest["language"],
            "speed": manifest["speed"],
            "auto_emotion": False,
            "voice": {"source": "custom", "voice_id": voice},
        }
        created = await json_response(
            await client.post(
                CLOUD_BASE + "/audio/v1/speech/jobs",
                headers={**headers, "Idempotency-Key": str(identity)},
                json=body,
            )
        )
        remote = created.get("task_id")
        if not isinstance(remote, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", remote):
            raise SpeechError("speech_provider_protocol")
        await save_remote(remote)
        for _ in range(300):
            result = await json_response(
                await client.get(CLOUD_BASE + "/audio/v1/speech/jobs/" + remote, headers=headers)
            )
            task = result.get("task", {})
            if task.get("status") == "succeeded":
                return await download(client, cloud_asset_url(task["output_url"]))
            if task.get("status") in {"failed", "cancelled"}:
                raise SpeechError("speech_generation_failed")
            if task.get("status") not in {"queued", "generating"}:
                raise SpeechError("speech_provider_protocol")
            await asyncio.sleep(3)
        raise SpeechError("speech_outcome_unknown")

    async def _cloud_voice(self, client, headers, card, manifest, key):
        media = "audio/wav" if manifest["reference"].endswith("wav") else "audio/mpeg"
        asset = {
            "file_name": manifest["reference"],
            "content_type": media,
            "file_size": len(card.audio),
        }
        upload = await json_response(
            await client.post(CLOUD_BASE + "/audio/v1/upload_urls", headers=headers, json=asset)
        )
        # Signed object storage requests never carry the provider's bearer key.
        result = await client.put(
            cloud_asset_url(upload["upload_url"]),
            content=card.audio,
            headers={"Content-Type": media},
        )
        if not result.is_success:
            raise SpeechError("speech_reference_upload_failed")
        registered = await json_response(
            await client.post(
                CLOUD_BASE + "/audio/v1/assets",
                headers=headers,
                json={**asset, "object_key": upload["object_key"], "duration_ms": card.duration_ms},
            )
        )
        created = await json_response(
            await client.post(
                CLOUD_BASE + "/audio/v1/voices",
                headers={
                    **headers,
                    "Idempotency-Key": str(uuid5(card.world_id, "livingworld:voice:v1:" + key)),
                },
                json={"asset_id": registered["asset"]["asset_id"], "name": manifest["name"]},
            )
        )
        voice = created.get("voice", {}).get("voice_id")
        if not isinstance(voice, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", voice):
            raise SpeechError("speech_provider_protocol")
        return voice
