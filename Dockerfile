# Read-only web demo of Supersede (fictional data). Works on Hugging Face Spaces (Docker SDK, port 7860),
# Render, Fly.io or any Docker host.
FROM python:3.12-slim

# Hugging Face Spaces runs containers as user 1000; a non-root user is good practice anywhere.
RUN useradd -m -u 1000 user
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY examples/store ./examples/store
COPY web ./web

ENV PORT=7860 \
    SUPERSEDE_DB=/app/examples/store/supersede-demo.relate \
    PYTHONUNBUFFERED=1
EXPOSE 7860
USER user
CMD ["python", "web/app.py"]
