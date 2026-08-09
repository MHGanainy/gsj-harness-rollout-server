# gsj-mcp-service image (CP-29, ADR-0040(a)).
#
# Self-contained for egress-restricted hosts: the pinned MiniLM snapshot is
# baked at build time and the container runs fully offline (HF_HUB_OFFLINE).
# Build on the workstation, ship with the CP-26 recipe (0.2.0 = CP-33:
# /admin/reindex + source.owner gsj-staging):
#   DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build -t gsj-mcp-service:0.2.0 .
#   docker save gsj-mcp-service:0.2.0 | ssh h200-admin docker load
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

# Bake the pinned embedding model; keep in sync with config.yaml
# embedding.revision. The runtime never downloads anything.
ENV HF_HOME=/opt/hf-cache
ARG MINILM_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
RUN http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= \
    python -c "from huggingface_hub import snapshot_download; \
    snapshot_download('sentence-transformers/all-MiniLM-L6-v2', \
    revision='${MINILM_REVISION}')" \
    && chmod -R a+rX /opt/hf-cache
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY gsj_mcp_service ./gsj_mcp_service
COPY config.yaml ./config.yaml

# The compose runs this with network_mode: host and user 1000 (H200 uid
# topology — see compose.yml); nothing here assumes root at runtime.
RUN mkdir -p /app/data && chmod -R a+rwX /app/data
ENV HOME=/tmp
CMD ["python", "-m", "gsj_mcp_service", "--config", "/app/config.yaml"]
