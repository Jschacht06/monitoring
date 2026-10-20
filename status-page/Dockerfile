FROM python:3.14.8-slim-trixie
WORKDIR /app
COPY server.py style.css ./
USER 65534:65534
EXPOSE 8080
CMD ["python", "-B", "server.py"]
