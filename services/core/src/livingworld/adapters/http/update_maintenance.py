"""Drain complete request lifetimes, including streaming responses."""

from starlette.responses import JSONResponse


class UpdateMaintenanceMiddleware:
    def __init__(self, app, maintenance):
        self.app, self.maintenance = app, maintenance

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].startswith("/system/"):
            await self.app(scope, receive, send)
            return
        with self.maintenance.operation() as admitted:
            if not admitted:
                await JSONResponse(
                    {"detail": "desktop_update_in_progress"},
                    status_code=503,
                    headers={"Retry-After": "5"},
                )(scope, receive, send)
                return
            await self.app(scope, receive, send)
