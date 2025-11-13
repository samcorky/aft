# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Update package index and install system dependencies
# Using retries for better reliability with network issues
RUN apt-get update || apt-get update || apt-get update
RUN apt-get install -y --no-install-recommends \
        gcc \
        default-libmysqlclient-dev \
        default-mysql-client \
        pkg-config \
        build-essential \
        curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app

# Fix line endings and make startup script executable
RUN sed -i 's/\r$//' startup.sh \
    && chmod +x startup.sh \
    && chmod -R u+w /app \
    && chown -R app:app /app

USER app

# Expose the port Flask runs on
EXPOSE 5000

# Command to run the application
CMD ["./startup.sh"]