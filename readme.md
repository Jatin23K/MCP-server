# FastMCP Server

A high-performance file and context management server built with FastAPI.

## Features

- 🚀 FastAPI-based RESTful API
- 🔐 JWT Authentication & API Key Support
- 📁 File upload/download with versioning
- 🔍 Full-text search and metadata management
- 📊 Monitoring and metrics (Prometheus)
- 📝 Interactive API documentation (Swagger UI & ReDoc)
- 🐳 Docker support
- 🔄 Background task processing
- 🔒 Rate limiting and security best practices

## Prerequisites

- Python 3.8+
- pip (Python package manager)
- Redis (for rate limiting and caching)
- (Optional) Docker & Docker Compose

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd mcp-server
   ```

2. **Create and activate a virtual environment**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # Linux/MacOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Initialize the database**
   ```bash
   # This will create the SQLite database and tables
   python -m app.db.init_db
   ```

## Configuration

Edit the `.env` file to configure the server:

```env
# Server Configuration
FASTAPI_ENV=development
UVICORN_HOST=0.0.0.0
UVICORN_PORT=8000

# Security
JWT_SECRET_KEY=your-secret-key-change-this-in-production

# File Storage
UPLOAD_DIR=./data/files
MAX_FILE_SIZE_MB=100

# Database
DATABASE_URL=sqlite:///./mcp.db

# Redis
REDIS_URL=redis://localhost:6379/0
```

## Running the Server

### Development Mode

```bash
# Windows
start_server.bat

# Linux/MacOS
chmod +x start_server.sh
./start_server.sh
```

The server will be available at http://localhost:8000

### Production Mode

For production, use a production ASGI server like uvicorn with gunicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Or using Docker:

```bash
docker-compose up --build -d
```

## API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Authentication

The API uses JWT for authentication. To authenticate:

1. Get an access token:
   ```
   POST /api/v1/auth/token
   Content-Type: application/x-www-form-urlencoded
   
   username=admin&password=yourpassword
   ```

2. Use the token in subsequent requests:
   ```
   Authorization: Bearer <your_token>
   ```

Or use API Key authentication:
```
X-API-Key: your-api-key
```

## File Operations

### Upload a File
```
POST /api/v1/files/upload
Content-Type: multipart/form-data

file: <file>
path: (optional) path/to/store/file
overwrite: false
```

### List Files
```
GET /api/v1/files?path=documents
```

### Download a File
```
GET /api/v1/files/download?path=documents/report.pdf
```

## Monitoring

- **Health Check**: `GET /health`
- **Metrics**: `GET /metrics`

## Development

### Running Tests
```bash
pytest tests/
```

### Code Formatting
```bash
black .
isort .
```

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.