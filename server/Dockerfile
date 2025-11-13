# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Update package index and install system dependencies
# Using --fix-missing and retries for better reliability
RUN for i in 1 2 3; do \
        apt-get update --fix-missing && \
        apt-get install -y --no-install-recommends \
            gcc \
            default-libmysqlclient-dev \
            pkg-config \
            build-essential \
            curl \
        && break || sleep 5; \
    done && \
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

# Make startup script executable and set ownership and permissions
RUN chmod +x startup.sh \
    && chmod -R u+w /app \
    && chown -R app:app /app

USER app

# Expose the port Flask runs on
EXPOSE 5000

# Command to run the application
CMD ["./startup.sh"]