FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for compilation and cryptography tools
RUN apt-get update && apt-get install -y \
    build-essential \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Ensure the data directory exists for the SQLite database
RUN mkdir -p data/db

# Set environment variables
ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=8000

# Expose the API port
EXPOSE 8000

# Run the FastAPI server using uvicorn
CMD ["python3", "backend/main.py"]
