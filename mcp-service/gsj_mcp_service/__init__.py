"""gsj-mcp-service — the external MCP service (CP-29, ADR-0040).

Standalone: serves the four `gsj` tools over streamable-http, ingesting the
frozen case dataset from staging Forgejo and ranking MiniLM embeddings under
token-scoped page cutoffs. Zero imports from ``gsj.envloader`` — the coupling
to the library is the HTTP contract and the token format only (extractable to
its own repository as-is).
"""

__version__ = "0.1.0"
