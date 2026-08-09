# ============================================================
# Ombre Brain Docker Build
# ============================================================

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from mcp.server.fastmcp import FastMCP"

COPY *.py .
COPY config.example.yaml ./config.yaml

VOLUME ["/opt/render/project/src/buckets"]

ENV OMBRE_TRANSPORT=streamable-http
ENV OMBRE_BUCKETS_DIR=/opt/render/project/src/buckets

EXPOSE 8000

# secure_server fails closed unless OMBRE_MCP_TOKEN is configured.
CMD ["python", "secure_server.py"]
