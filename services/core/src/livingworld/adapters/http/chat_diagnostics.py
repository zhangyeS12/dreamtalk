"""Catch chat HTTP validation/save failures without logging request or response bodies."""

from fastapi.routing import APIRoute

from livingworld.application.chat_diagnostics import chat_diagnostic_scope, chat_phase


def diagnostic_route(logger):
    class DiagnosedChatRoute(APIRoute):
        def get_route_handler(self):
            handle = super().get_route_handler()

            async def diagnosed(request):
                with chat_diagnostic_scope(logger, endpoint=self.name):
                    chat_phase("request")
                    return await handle(request)

            return diagnosed

    return DiagnosedChatRoute
