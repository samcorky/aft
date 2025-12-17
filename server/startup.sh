#!/bin/bash
# Startup script to run migrations before starting the application

set -e  # Exit on error

# Copy default background images if the backgrounds directory is empty
BACKGROUNDS_DIR="/var/www/images/backgrounds"
DEFAULTS_DIR="/app/backgrounds-defaults"

if [ -d "$DEFAULTS_DIR" ] && [ -n "$(ls -A "$DEFAULTS_DIR" 2>/dev/null)" ]; then
    echo "Checking backgrounds directory..."
    mkdir -p "$BACKGROUNDS_DIR"
    
    # Check if directory is empty (excluding hidden files)
    if [ -z "$(ls -A "$BACKGROUNDS_DIR" 2>/dev/null)" ]; then
        echo "Copying default background images..."
        cp "$DEFAULTS_DIR"/* "$BACKGROUNDS_DIR/" 2>/dev/null || true
        echo "Default background images copied."
    else
        echo "Background images already exist."
    fi
fi

echo "Waiting for database to be ready..."

# Wait for database to be available
python << END
import time
import sys
from database import engine

max_retries = 30
retry_count = 0

while retry_count < max_retries:
    try:
        engine.connect()
        print("Database connection successful!")
        sys.exit(0)
    except Exception as e:
        retry_count += 1
        print(f"Database not ready (attempt {retry_count}/{max_retries}): {e}")
        time.sleep(2)

print("Could not connect to database after maximum retries")
sys.exit(1)
END

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 300 app:app
