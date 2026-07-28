FROM python:3.11-slim

WORKDIR /app

# Copy only what's needed to install and run Sancho Fetch. .dockerignore excludes the
# rest (references-other-projects, tests, .git, etc) so the image stays small.
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY hosting /app/hosting

RUN pip install --no-cache-dir .

ENV PORT=10000
EXPOSE 10000

# Render routes health checks to /health which the core _HttpHandler already
# serves, so no extra wiring needed.
CMD ["python", "hosting/server.py"]
