# SAT-SA single-image build: dashboard bundle + Python API in one container.
# Offline build: place wheels in ./wheels and node modules tarball handling is documented in README;
# `docker build --network none` works once ./wheels is populated (make wheels).

# ---------- stage 1: dashboard ----------
FROM node:22-alpine AS dashboard
WORKDIR /ui
COPY dashboard/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY dashboard/ ./
RUN npm run build

# ---------- stage 2: api ----------
FROM python:3.11-slim AS api
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    SATSA_CONFIG_DIR=/app/config
WORKDIR /app

# Build tools only if a wheel has to be compiled (hdbscan extra); harmless otherwise.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY wheels/ /wheels/
COPY satsa/ ./satsa/
COPY simulator/ ./simulator/
COPY validation/ ./validation/
COPY config/ ./config/

# Prefer vendored wheels (true air-gap); fall back to the index when none are present.
RUN if ls /wheels/*.whl >/dev/null 2>&1; then \
      pip install --no-cache-dir --no-index --find-links /wheels ".[dev]"; \
    else \
      pip install --no-cache-dir ".[dev]"; \
    fi

COPY --from=dashboard /ui/dist ./dashboard/dist

RUN useradd --create-home --uid 10001 satsa \
    && mkdir -p data/incoming data/processed data/synthetic data/ground_truth models reports logs \
    && chown -R satsa:satsa /app
USER satsa

EXPOSE 8000
CMD ["uvicorn", "satsa.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
