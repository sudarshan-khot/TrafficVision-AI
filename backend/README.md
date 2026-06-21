# TrafficVision AI — Backend API

This is the Python FastAPI backend for the TrafficVision AI system. It manages the database migrations, processes traffic image uploads, runs ML model inferences (YOLOv8 & PaddleOCR), and serves REST API endpoints for traffic violation enforcement.

---

## 1. Prerequisites

- **Python 3.11**
- **Docker Engine** (for running PostgreSQL and MinIO background services)

---

## 2. Setup and Installation

### A. Create a Virtual Environment and Install Dependencies
Navigate to the `backend/` directory:
```bash
cd backend
```

Create a python virtual environment and activate it:
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Unix / macOS
python3 -m venv .venv
source .venv/bin/activate
```

Install the package dependencies:
```bash
pip install -r requirements.txt
```

### B. Environment Configuration
Copy `.env.example` from the repository root into `backend/.env` (or configure your system environment variables directly):
```bash
cp ../.env.example .env
```

Ensure the configuration variables point to the correct database and object storage hosts. For running the backend locally while Postgres/MinIO are running in Docker, the following defaults are recommended in `backend/.env`:
```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/trafficvision
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=traffic-images
MINIO_SECURE=false
MODEL_DIR=../trained_models
APP_ENV=development
LOG_LEVEL=INFO
```

### C. Model Weights Placement
Make sure the required model weights exist in the `trained_models/` folder at the root of the project (or the folder specified in `MODEL_DIR`):
- `yolov8m.pt` (vehicle and plate detection)
- `helmet_detection.pt` (rider compliance classification)

You can download `yolov8m.pt` and clone it as a temporary placeholder by running:
```bash
python -c "
import urllib.request, os, shutil
os.makedirs('../trained_models', exist_ok=True)
print('Downloading YOLOv8m...')
urllib.request.urlretrieve('https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8m.pt', '../trained_models/yolov8m.pt')
print('Creating helmet_detection placeholder...')
shutil.copy('../trained_models/yolov8m.pt', '../trained_models/helmet_detection.pt')
print('Done!')
"
```

---

## 3. Starting the Services

### Step 1: Start PostgreSQL and MinIO
From the **root** of the repository, start Postgres and MinIO in detached mode using Docker Compose:
```bash
docker compose up -d postgres minio
```

### Step 2: Apply Database Migrations
Run the Alembic migrations to construct the database schema and tables locally:
```bash
alembic upgrade head
```

### Step 3: Run the Backend Server
Start the Uvicorn development server:
```bash
uvicorn app.main:app --reload --port 8000
```

The backend is now available at [http://localhost:8000](http://localhost:8000).
Interactive Swagger documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## 4. Running Tests

The test suite runs with pytest and utilizes an in-memory SQLite database and mocked storage services. To execute all backend tests:
```bash
pytest
```

---

## 5. API Routes Documentation

The API includes the following core endpoints:

### Health Router
* **`GET /health`**
  - **Description**: Verifies that the API server, database connection, and S3 object storage are fully operational.
  - **Response Payload**:
    ```json
    {
      "status": "healthy",
      "database": "ok",
      "storage": "ok",
      "timestamp": "2026-06-20T17:00:00Z"
    }
    ```

### Upload Router
* **`POST /upload-image`**
  - **Description**: Receives a raw traffic snapshot file, validates that it is a valid JPEG/PNG image, uploads the original object to the MinIO `traffic-images` bucket, and generates a tracking ID.
  - **Request**: Multipart Form Data (`file: UploadFile`).
  - **Response Payload**:
    ```json
    {
      "image_id": "84c8a2b5-5b8d-4a1e-87a2-f67c3bdae539",
      "bucket": "traffic-images",
      "object_key": "original/84c8a2b5-5b8d-4a1e-87a2-f67c3bdae539.jpg"
    }
    ```

### Analysis Router
* **`POST /analyze`**
  - **Description**: Triggers the detection pipeline for a previously uploaded image.
    1. Loads the image from storage.
    2. Runs YOLOv8m to detect vehicles (`motorcycle`, `car`, `truck`, `bus`), `person` riders, and `number_plate` objects.
    3. Crops riders and executes the secondary fine-tuned YOLO model to evaluate helmet compliance.
    4. Crops number plates and runs OCR to read plate characters.
    5. Feeds detections to the Violation Engine to verify infraction rules (e.g. helmet non-compliance, rider count violation).
    6. Generates cropped violation evidence images and uploads them.
    7. Stores vehicles and violations in PostgreSQL.
  - **Request Body**:
    ```json
    {
      "image_id": "84c8a2b5-5b8d-4a1e-87a2-f67c3bdae539"
    }
    ```
  - **Response Payload**:
    ```json
    {
      "status": "success",
      "violations_count": 1,
      "violations": [
        {
          "id": "c16fae54-bfcd-4c8d-ae28-8d2a5f70a831",
          "violation_type": "HELMET_NON_COMPLIANCE",
          "confidence": 0.89,
          "plate_number": "MH12DE1433"
        }
      ]
    }
    ```

### Violations Router
* **`GET /violations`**
  - **Description**: Fetches list of violations with support for pagination, sorting, and database filters.
  - **Query Parameters**:
    - `page` (int, default: 1)
    - `limit` (int, default: 10)
    - `violation_type` (str, optional)
    - `start_date` (datetime, optional)
    - `end_date` (datetime, optional)
    - `plate_number` (str, optional)
  - **Response Payload**: Returns a JSON object with metadata pagination fields and a `items` list of matching violations.

* **`GET /violations/{violation_id}`**
  - **Description**: Retrieves detailed info on a specific violation ID, including corresponding vehicle bounding boxes, crop image urls, and raw snapshots.
  - **Response Payload**: Returns detailed violation model attributes.

### Analytics Router
* **`GET /analytics`**
  - **Description**: Aggregates violation data over a configurable time window to display on front-end dashboards. Includes total infraction metrics, counts segmented by vehicle types, and rider helmet compliance ratios.
  - **Query Parameters**:
    - `start_date` (datetime, optional)
    - `end_date` (datetime, optional)
    - `by_date` (bool, default: false) - Returns timeline series if enabled.
