FROM python:3.11-slim

WORKDIR /app

# curl is needed for the container healthcheck defined in docker-compose.yml
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

# FastMCP's streamable-http transport runs its own ASGI server internally
# (via mcp.run()), so there's no separate `uvicorn ...:app` invocation here
# the way there is for the `app` service.
CMD ["python", "server.py"]
