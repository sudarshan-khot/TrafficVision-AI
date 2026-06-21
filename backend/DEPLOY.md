# Backend Deployment (Railway / Render / Docker Compose)

This document provides detailed guidelines for deploying the TrafficVision AI backend, managing its ML models, and configuring its multi-container orchestrations.

---

## 1. Containerization Strategy

The backend runs inside a Docker container configured for performance, predictability, and minimal image size.

### Multi-Stage Dockerfile Design
The build is split into two stages:
1. **Builder Stage (`python:3.11-slim`)**:
   - Uses the extremely fast package installer **uv** to install all python dependencies.
   - Installs system-level compilation tools (`gcc`, `g++`, `libglib2.0-0`, `libgl1`, `curl`) required by OpenCV and other modules at build time.
   - Installs dependencies into a clean virtual environment `/app/.venv` to isolate packages.
2. **Runtime Stage (`python:3.11-slim`)**:
   - Excludes compilation tools to keep the container lightweight.
   - Installs only necessary runtime libraries (`libglib2.0-0`, `libgl1`, `libgomp1`) required for OpenCV and YOLO/PyTorch inference.
   - Copies the complete virtual environment `/app/.venv` from the builder stage.
   - Sets the path variables to use this virtual environment by default.
   - Exposes port `8000`.

---

## 2. ML Model Deployment and Lifecycle

The system utilizes two distinct ML model weight files that must be supplied for inference.

### Model Weights Specification
- **Vehicle and Feature Detector (`yolov8m.pt`)**: A pre-trained Ultralytics YOLOv8 medium model. It is filtered in python to focus on domain-specific classes (`motorcycle`, `car`, `truck`, `bus`, `person`, and `number_plate`).
- **Helmet Compliance Classifier (`helmet_detection.pt`)**: A custom fine-tuned YOLOv8 model that accepts cropped images of riders (people associated with motorcycles) and classifies their helmet status (`with_helmet` or `without_helmet`).

### Volume Mounting Strategy
Because model weights are large binary files (approx. 50MB+ each) and subject to training updates:
- They are **not** baked into the Docker image. This avoids bloated image sizes and long build times.
- Instead, the weights are mounted at runtime. In Docker Compose, the local host directory `./trained_models` is mounted as read-only to `/app/trained_models:ro` inside the container.
- For cloud platforms (Railway/Render), weights must be mounted using persistent volumes or retrieved from cloud storage during startup.

### Lifecycle & Memory Management
- **Validation**: On container boot, the startup script checks that both model files exist in the designated `MODEL_DIR`. If either is missing, the process prints a detailed error and exits with code 1 immediately.
- **Single Instantiation**: The model weights are loaded into memory exactly once at class instantiation of the `DetectionService` and kept in RAM/GPU-memory for the entire lifetime of the process. This prevents severe overhead on subsequent API requests.

---

## 3. Container Orchestration (Docker Compose)

For local development and staging environments, the backend is orchestrated along with its required services using Docker Compose.

```
┌──────────────────────────────────────────────────────────────┐
│                      Docker Compose                          │
│                                                              │
│  ┌────────────────┐   ┌────────────────┐   ┌──────────────┐  │
│  │   PostgreSQL   │◄──┤  FastAPI API   ├──►│    MinIO     │  │
│  │    (5432)      │   │     (8000)     │   │ (9000/9001)  │  │
│  └────────────────┘   └───────▲────────┘   └──────────────┘  │
│                               │                              │
│                               │ (volume mount)               │
│                               ▼                              │
│                     ┌──────────────────┐                     │
│                     │  trained_models/ │                     │
│                     └──────────────────┘                     │
└──────────────────────────────────────────────────────────────┘
```

### Orchestrated Services
- **`postgres:16-alpine`**: 
  - An Alpine-based PostgreSQL instance.
  - Exposes port `5432`.
  - Persists data to a named Docker volume (`pgdata`).
  - Configured with a health check running `pg_isready` every 5 seconds.
- **`minio/minio:latest`**: 
  - High-performance, S3-compatible object storage.
  - Exposes API port `9000` and admin console Web UI port `9001`.
  - Persists storage files to a named Docker volume (`miniodata`).
  - Configured with a health check testing `mc ready local` to verify availability.
- **`backend`**:
  - Built from `backend/Dockerfile` with app environment configurations.
  - Exposes port `8000` to the host.
  - Uses `depends_on` with `service_healthy` conditions for both `postgres` and `minio` to ensure it only boots once database and object storage are ready to accept connections.

---

## 4. Environment Variables

Configure the following variables in your deployment environment or `.env` file:

| Variable | Description | Default / Example Value |
| :--- | :--- | :--- |
| `DATABASE_URL` | Async connection string for PostgreSQL | `postgresql+asyncpg://user:pass@postgres:5432/trafficvision` |
| `MINIO_ENDPOINT` | Hostname and port of MinIO | `minio:9000` |
| `MINIO_ACCESS_KEY` | Access key credential for MinIO | `minioadmin` |
| `MINIO_SECRET_KEY` | Secret key credential for MinIO | `minioadmin` |
| `MINIO_BUCKET` | Name of the bucket to store images | `traffic-images` |
| `MINIO_SECURE` | Set to true if endpoint runs SSL | `false` |
| `CORS_ALLOWED_ORIGINS` | Permitted frontend origin list | `http://localhost:5173` |
| `MODEL_DIR` | Path to weights folder in container | `trained_models` |
| `APP_ENV` | Application mode (`development` / `production` / `test`) | `production` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

---

## 5. Cloud Platform Deployment

### Railway

1. Create a new Railway project and add a **PostgreSQL** database service.
2. Add a **MinIO** service or configure a connection to AWS S3.
3. Deploy the backend from your GitHub repository, setting the root directory to `backend/`.
4. Provision a volume for the backend service at `/app/trained_models` and upload the model weight files (`yolov8m.pt` and `helmet_detection.pt`) into it, or download them in a custom start script.
5. Apply the environment variables listed above.

### Render

1. Create a **PostgreSQL** database service.
2. Create a **Web Service** using the Docker runtime.
3. Set the Dockerfile path to `backend/Dockerfile` and the build context to `backend/`.
4. Configure a persistent disk/volume mounted at `/app/trained_models` to hold the model weights.
5. Set environment variables.
6. Build and deploy.

---

## 6. Startup Behavior

On startup, the container automatically executes the following sequences before opening the API socket:
1. **Migrations**: programmatically runs `alembic upgrade head` to bring the database schema to the latest version.
2. **Object Storage**: initializes the MinIO client, checks for the presence of the configured bucket, and creates it if it does not exist.
3. **Model Validation**: verifies that all configured model weight files are available for loading.

---

## 7. Health Check

Use `GET /health` for load balancer and runtime probes. It returns a `200 OK` status with a JSON payload verifying database and storage connectivity status.

