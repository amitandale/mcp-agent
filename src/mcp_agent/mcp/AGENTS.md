# Scope rules for `src/mcp_agent/mcp/`

This folder owns protocol-layer plumbing. Follow root guidance and:

- Reuse the existing client proxies, connection manager, server registry, and transports; avoid bespoke MCP protocol code.
- When adding servers or transports, thread them through the shared registry/config rather than hardcoding endpoints.
- Keep APIs consistent with the MCP spec and with `MCPApp` expectations; changes should be additive and documented.
- Do not mix domain-specific logic here—limit to protocol, transport, and registration concerns.
