FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite and backups
RUN mkdir -p /app/data

# Expose port (NiceGUI default)
EXPOSE 8080

# Environment
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Run the application
CMD ["python", "main.py"]
