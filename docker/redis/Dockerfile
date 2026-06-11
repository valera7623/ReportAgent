# Built from local reportagent-app image — avoids Docker Hub metadata lookup.
FROM reportagent-app:latest

RUN apt-get update \
    && apt-get install -y --no-install-recommends redis-server \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data

VOLUME /data
EXPOSE 6379

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD redis-cli ping | grep -q PONG

CMD ["redis-server", "--appendonly", "yes", "--dir", "/data"]
