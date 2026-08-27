# Production Dockerfile for Secure Attendance System
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and buffer outputs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for OpenCV, PostgreSQL, and C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from root
COPY requirements.txt /app/requirements.txt

# Install CPU-optimized PyTorch first (reduces image size from 2.5GB to ~600MB)
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Copy secure_attendance app code into working directory
COPY secure_attendance /app/secure_attendance
WORKDIR /app/secure_attendance

EXPOSE 8000

# Run database migrations and start Gunicorn with 4 worker processes
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn --bind 0.0.0.0:8000 --workers 4 --threads 2 secure_attendance.wsgi:application"]
