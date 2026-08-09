FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && mcp2xiaozhi version

COPY start_bridge.py .

RUN useradd --create-home --uid 10001 bridge \
    && chown -R bridge:bridge /app

USER bridge

CMD ["python", "start_bridge.py"]
