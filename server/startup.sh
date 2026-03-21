#!/bin/bash
# Startup script to run migrations before starting the application

set -e  # Exit on error

echo "Verifying backgrounds directory..."
BACKGROUNDS_DIR="/var/www/images/backgrounds"
mkdir -p "$BACKGROUNDS_DIR"

if [ -n "$(ls -A "$BACKGROUNDS_DIR" 2>/dev/null)" ]; then
    echo "✓ Background images available ($(ls -1 "$BACKGROUNDS_DIR" | wc -l) files)"
else
    echo "⚠ No background images found - users can upload custom images"
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
# Use gthread workers for Flask-SocketIO in threading mode.
# Sync workers can be killed by Gunicorn when handling long-lived websocket requests.
# Redis message queue keeps Socket.IO broadcasts synchronized across worker processes.
# Timeout remains high for long operations like large database restores.
exec gunicorn --bind 0.0.0.0:5000 --worker-class gthread --workers 4 --threads 8 --timeout 1800 app:app
