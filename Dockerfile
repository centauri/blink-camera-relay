FROM node:22-bookworm-slim AS onvif-build
WORKDIR /build
COPY vendor/onvif/package*.json ./
RUN npm ci
COPY vendor/onvif/src ./src
COPY vendor/onvif/ws-discovery.ts vendor/onvif/tsconfig.json ./
RUN npx tsc && npm prune --omit=dev
RUN node -e "fetch('https://raw.githubusercontent.com/nodejs/node/'+process.version+'/LICENSE').then(async r=>{if(!r.ok)throw Error('Node license download failed');require('fs').writeFileSync('/build/NODE-LICENSE',await r.text())})"
FROM bluenviron/mediamtx:1.21.1 AS media
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 BRIDGE_CONTAINER=1 BRIDGE_DATA=/data BRIDGE_RUNTIME=/run/blink
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends ffmpeg ca-certificates tini libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY vendor/blinkpy /opt/blinkpy
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock /opt/blinkpy
COPY --from=onvif-build /usr/local/bin/node /usr/local/bin/node
COPY --from=onvif-build /build/NODE-LICENSE /usr/share/blink-camera-relay/NODE-LICENSE
COPY --from=onvif-build /build/dist /app/vendor/onvif/dist
COPY --from=onvif-build /build/node_modules /app/vendor/onvif/node_modules
COPY --from=media /mediamtx /usr/local/bin/mediamtx
COPY vendor/onvif/LICENSE vendor/onvif/MEDIAMTX-LICENSE /usr/share/blink-camera-relay/onvif/
COPY LICENSE NOTICE THIRD-PARTY.md /usr/share/blink-camera-relay/
COPY bridge /app/bridge
RUN mkdir -p /data /run/blink
EXPOSE 8787 8080 8555 3702/udp
VOLUME ["/data"]
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["python", "/app/bridge/web.py"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import socket; socket.create_connection(('127.0.0.1',8787),3).close()"
FROM runtime AS source-collector
COPY scripts/collect-debian-sources.sh /tmp/collect-debian-sources.sh
RUN sh /tmp/collect-debian-sources.sh && tar -czf /corresponding-sources.tar.gz -C / sources
FROM scratch AS sources
COPY --from=source-collector /corresponding-sources.tar.gz /
FROM runtime AS final
