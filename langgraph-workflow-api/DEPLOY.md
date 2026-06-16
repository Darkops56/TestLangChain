# Deployment Guide

## Local Development

1. **Create virtual environment**
   ```bash
   python -m venv .venv
   ```

2. **Activate the environment**
   ```bash
   # Windows
   .venv\Scripts\activate
   # Unix / macOS
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the development server**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set your Gemini API key:
   ```
   GEMINI_API_KEY=your-key-here
   GEMINI_MODEL=gemini-2.0-flash
   ```

6. **Open API docs**
   Visit [http://localhost:8000/docs](http://localhost:8000/docs)

## Production Deployment

### Process Manager (Gunicorn)

Install gunicorn and use it with uvicorn workers:

```bash
pip install gunicorn
gunicorn -k uvicorn.workers.UvicornWorker app.main:app --workers 4 --bind 0.0.0.0:8000
```

### Environment Variables

Set the following variables in your production environment:

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key for AI agent |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model identifier |
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `8000` | Server port |

### CORS Configuration

Update `app/main.py` to restrict CORS origins for production:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Docker Deployment

Create a `Dockerfile` at the project root:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t langgraph-workflow-api .
docker run -p 8000:8000 langgraph-workflow-api
```
