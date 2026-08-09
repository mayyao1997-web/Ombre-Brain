# ============================================================
# Ombre Brain + StackChan 187 bridge
# ============================================================

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from mcp.server.fastmcp import FastMCP" \
    && mcp2xiaozhi version

COPY *.py .
COPY bridge/start_bridge.py ./bridge/start_bridge.py
COPY config.example.yaml ./config.yaml

VOLUME ["/opt/render/project/src/buckets"]

ENV OMBRE_TRANSPORT=streamable-http
ENV OMBRE_BUCKETS_DIR=/opt/render/project/src/buckets

EXPOSE 8000

# Ombre always starts. The bridge starts only when MCP_ENDPOINT_OMBRE_187 exists.
CMD ["python", "combined_service.py"]
