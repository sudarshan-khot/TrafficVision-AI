# TrafficVision AI

TrafficVision AI is an intelligent traffic monitoring and enforcement system. It automatically detects vehicles, identifies riders without helmets on motorcycles, reads license plates using OCR, and records traffic violations.

## Prerequisites

- **Docker Engine** (Desktop or Daemon) installed and running.
- **Python 3.11** (optional, for running backend/tests locally without Docker).
- **Node.js 18+** (for running the frontend locally).

---

## 1. Environment Configuration

Copy the example environment file at the root to `.env`:

```bash
cp .env.example .env
```

The default values are configured for local development and Docker Compose. If you need custom database credentials or a custom MinIO endpoint, update them in `.env`.

---

## 2. Model Weights Setup

The backend requires model weights to start. The model files must be placed in the `trained_models/` folder:

1. **YOLOv8m base model**: `yolov8m.pt` (used for detecting vehicles, persons, and number plates).
2. **Helmet Detection model**: `helmet_detection.pt` (fine-tuned model for classifying helmet compliance on riders).

### Automatic Script
You can download the base model and create a placeholder for the helmet model by running:

```bash
python -c "
import urllib.request, os, shutil
os.makedirs('trained_models', exist_ok=True)
print('Downloading YOLOv8m...')
urllib.request.urlretrieve('https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8m.pt', 'trained_models/yolov8m.pt')
print('Creating helmet_detection placeholder...')
shutil.copy('trained_models/yolov8m.pt', 'trained_models/helmet_detection.pt')
print('Done!')
"
```

> [!NOTE]
> The placeholder model allows the application to boot and run inference. For actual helmet compliance classification, replace `trained_models/helmet_detection.pt` with your fine-tuned weights.

---

## 3. Starting the Services with Docker Compose

You can start the entire stack (Database, Object Storage, and Backend API) in detached mode:

```bash
docker compose up -d --build
```

### Verification
Verify that all services are running and healthy:

```bash
docker compose ps
```

To view backend service logs:

```bash
docker compose logs -f backend
```

---

## 4. Service Endpoints

Once the services are running, the following endpoints are available:

| Service | Endpoint / Link | Credentials / Info |
| :--- | :--- | :--- |
| **Backend API** | [http://localhost:8000](http://localhost:8000) | FastAPI App |
| **API Docs (Swagger)** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive API exploration |
| **MinIO Console** | [http://localhost:9001](http://localhost:9001) | **Username:** `minioadmin` <br> **Password:** `minioadmin` |
| **MinIO API** | [http://localhost:9000](http://localhost:9000) | S3-compatible API endpoint |
| **PostgreSQL Database** | `localhost:5432` | **Database:** `trafficvision` <br> **User:** `user` <br> **Password:** `pass` |

---

## 5. Development Mode (Local Execution)

If you wish to run the backend or frontend locally instead of inside Docker:

### A. Run Database & Storage in Docker
Only start PostgreSQL and MinIO containers:
```bash
docker compose up -d postgres minio
```

### B. Run Backend API Locally
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment, then install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # On Windows
   source .venv/bin/activate  # On Unix/macOS
   pip install -r requirements.txt
   ```
3. Run Alembic migrations:
   ```bash
   alembic upgrade head
   ```
4. Start the Uvicorn server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

### C. Run Frontend Locally
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   Open [http://localhost:5173](http://localhost:5173) in your browser.
