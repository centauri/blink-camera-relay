FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx tsc --project tsconfig.json

FROM bluenviron/mediamtx:1.21.1 AS mediamtx

FROM node:22-bookworm-slim AS runtime
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist
COPY mediamtx.yml ./mediamtx.yml
COPY LICENSE README.md MEDIAMTX-LICENSE /usr/share/onvif-protect-bridge/
COPY --from=mediamtx /mediamtx /usr/local/bin/mediamtx
EXPOSE 8080 8554 3702/udp
CMD ["node", "dist/src/server.js"]

FROM runtime AS source-collector
COPY collect-debian-sources.sh /tmp/collect-debian-sources.sh
RUN sh /tmp/collect-debian-sources.sh
FROM scratch AS sources
COPY --from=source-collector /sources /sources
FROM runtime AS final
