# gsj-mcp-service image (CP-29, ADR-0040(a)).
#
# Self-contained for egress-restricted hosts: the configured embedding model's snapshot is
# baked at build time and the container runs fully offline (HF_HUB_OFFLINE;
# Chroma telemetry is disabled in code — Settings(anonymized_telemetry=False)).
# Build on the workstation, ship with the CP-26 recipe (0.5.0 = CP-79: the
# decisions surface — a rii-dok v1 drop at decisions.path served as
# Randnummern at level 2 of docs/decisions-surface.md, search_decisions
# returning {query, k, hits, index_commit}, one fingerprint per collection
# so a drop never re-embeds the cases, the fetch bounded at 200·k; the
# synthetic 30 stay the no-path default and every existing store is reused
# as it is; 0.4.1 = CP-77: the indexer's two defects — both builders add in
# batches under chroma's 5,461-item ceiling with progress per batch, and
# every rebuild — and every start that loads or rebuilds the store — sweeps
# the HNSW directories chroma leaves behind; no config, contract or
# fingerprint change; published two-platform on GHCR at CP-79; 0.4.0 =
# CP-58: CP-57's configurable encoder + the store identity, config.yaml
# with the read credential; published multi-arch on GHCR at CP-61 — the
# amd64 half IS the H200's image, the arm64 half the CP-59 native build;
# 0.3.0 = CP-15: the ChromaDB backend, ADR-0016 — ≈ +310 MB installed vs
# 0.2.0; 0.2.0 = CP-33: /admin/reindex + source.owner gsj-staging):
#   DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build -t gsj-mcp-service:0.5.0-amd64 .
#   docker build -t gsj-mcp-service:0.5.0 .          # the native half on an arm64 workstation
#   docker save gsj-mcp-service:0.5.0-amd64 | ssh h200-admin docker load
# (or, since every tag from 0.4.0 is a two-platform index on GHCR, pull
# ghcr.io/mhganainy/gsj-mcp-service:0.5.0 — on the H200 through skopeo as
# uid 1000, estate/README.md)
FROM python:3.12-slim

# git: the ingester clones the case repos. Build-network hardening as in the
# predecessor's sandbox/Dockerfile (corrupting-middlebox networks): proxy env
# neutralized on every network RUN and apt over HTTPS (the python base ships
# CA roots).
RUN http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= sh -c ' \
        sed -i "s|http://deb.debian.org|https://deb.debian.org|g" \
            /etc/apt/sources.list.d/debian.sources \
        && apt-get update \
        && apt-get install -y --no-install-recommends git ca-certificates \
        && rm -rf /var/lib/apt/lists/*'

WORKDIR /app
COPY requirements.txt ./
RUN http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= \
    pip install --no-cache-dir -r requirements.txt \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Bake the pinned embedding model; keep BOTH args in sync with config.yaml
# embedding.model / embedding.revision (CP-57: the model is configuration —
# a different model is a build arg, not a Dockerfile edit). The runtime
# never downloads anything: HF_HUB_OFFLINE below, so a config naming a
# model this image did not bake fails at startup with the id named.
ENV HF_HOME=/opt/hf-cache
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ARG EMBEDDING_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
RUN http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= \
    python -c "from huggingface_hub import snapshot_download; \
    snapshot_download('${EMBEDDING_MODEL}', \
    revision='${EMBEDDING_REVISION}')" \
    && chmod -R a+rX /opt/hf-cache
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY gsj_mcp_service ./gsj_mcp_service
COPY config.yaml ./config.yaml

# The compose runs this with network_mode: host and user 1000 (H200 uid
# topology — see compose.yml); nothing here assumes root at runtime.
RUN mkdir -p /app/data && chmod -R a+rwX /app/data
ENV HOME=/tmp
CMD ["python", "-m", "gsj_mcp_service", "--config", "/app/config.yaml"]
