FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for ML libraries and compilation
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
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

# Command to run the application
CMD ["python", "backend/main.py"]
