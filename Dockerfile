FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY vendor/blinkpy /opt/blinkpy
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock /opt/blinkpy
COPY LICENSE NOTICE THIRD-PARTY.md /usr/share/blink-camera-relay/
COPY bridge /app
ENTRYPOINT ["python", "/app/app.py"]
CMD ["run"]

FROM runtime AS source-collector
COPY scripts/collect-debian-sources.sh /tmp/collect-debian-sources.sh
RUN sh /tmp/collect-debian-sources.sh

FROM scratch AS sources
COPY --from=source-collector /sources /sources
COPY LICENSE NOTICE THIRD-PARTY.md /notices/

FROM runtime AS final
