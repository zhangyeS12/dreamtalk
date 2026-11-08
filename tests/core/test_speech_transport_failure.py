"""Transport failures cross the provider port as uncertain speech outcomes."""

import asyncio

import httpx
import pytest
from livingworld.application.speech_contracts import SpeechError
from livingworld.infrastructure.speech_providers import IndexSpeechProviders


@pytest.mark.parametrize("transport", [True, False])
def test_provider_translates_transport_errors_without_changing_known_failures(transport):
    async def run():
        provider = IndexSpeechProviders(None, None)

        async def fail(*args):
            if transport:
                raise httpx.ReadTimeout("PRIVATE-TRANSPORT-DETAIL-CANARY")
            raise SpeechError("speech_local_unavailable")

        provider._synthesize = fail
        expected = "speech_status_lost" if transport else "speech_local_unavailable"
        with pytest.raises(SpeechError, match=f"^{expected}$"):
            await provider.synthesize(*([None] * 7))

    asyncio.run(run())
