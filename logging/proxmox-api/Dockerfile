FROM python:3.14.8-slim-trixie
WORKDIR /app
RUN mkdir -p /var/lib/collector && chown 65534:65534 /var/lib/collector
COPY collector.py ./
USER 65534:65534
ENTRYPOINT ["python", "-B", "-u", "/app/collector.py"]
