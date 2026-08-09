# CP-06 spike sandbox image: node + the predecessor's byte-exact pi pins.
# package.json/package-lock.json are verbatim copies of gsj-envloader
# sandbox/pi/ (@earendil-works/pi-coding-agent@0.83.0 + pi-mcp-extension@1.5.0,
# restored via npm ci — never bun, never a regenerated lock). The package
# entry after install is /opt/pi/node_modules/@earendil-works/pi-coding-agent/
# dist/cli.js — NEVER node_modules/.bin/pi (ADR-0008 D4(d): the extension's
# peer dependency overwrites the shim with legacy pi 0.73.x).
FROM node:22.16.0-bookworm-slim
WORKDIR /opt/pi
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
