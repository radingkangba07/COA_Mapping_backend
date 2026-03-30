FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy api-service (imported by backend via sys.path)
COPY services/api-service/ ./services/api-service/

ENV PYTHONPATH=/app/backend
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

WORKDIR /app/backend
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]