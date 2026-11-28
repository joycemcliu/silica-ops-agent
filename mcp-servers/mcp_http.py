"""Bearer-protected streamable HTTP transport for repository MCP servers."""

import hmac


class BearerAuth:
    def __init__(self, app, token):
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            given = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(given, self.expected):
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await self.app(scope, receive, send)


def serve_http(mcp, host, port, token):
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    if host not in ("127.0.0.1", "localhost", "::1"):
        # FastMCP's default host allowlist is for loopback listeners.
        mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    uvicorn.run(BearerAuth(mcp.streamable_http_app(), token), host=host, port=port)
