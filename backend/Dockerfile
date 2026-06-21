# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: builder
# Uses uv to install Python dependencies into /app/.venv.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system-level build tools needed by some Python packages at compile time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libglib2.0-0 \
        libgl1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency installation
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.cargo/bin:$PATH"

# Copy dependency files
COPY backend/pyproject.toml backend/requirements.txt ./

# Create virtual env and install requirements
RUN uv venv .venv && \
    uv pip install --python .venv/bin/python --no-cache -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime
# Slim final image — no build tools, no uv, just the app, weights, and its venv.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime-only system libraries required by OpenCV / PaddleOCR.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy the venv from the builder stage.
COPY --from=builder /app/.venv /app/.venv

# Make the venv's Python the default.
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# Copy application source code
COPY backend/ /app/

# Bake trained models into the image for Free Tier cloud platforms that lack volume mounts.
# Local development volume mounts will overwrite this directory, retaining dynamic updates.
COPY trained_models/ /app/trained_models/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
