#!/bin/sh
# Generate self-signed SSL certificates if they don't exist

SSL_DIR="/etc/nginx/ssl"
CERT_FILE="$SSL_DIR/cert.pem"
KEY_FILE="$SSL_DIR/key.pem"

# Create SSL directory if it doesn't exist
mkdir -p $SSL_DIR

# Generate self-signed certificate if it doesn't exist
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "Generating self-signed SSL certificate..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout $KEY_FILE \
        -out $CERT_FILE \
        -subj "/C=US/ST=State/L=City/O=AFT/CN=localhost" \
        2>/dev/null
    
    echo "SSL certificate generated successfully"
else
    echo "SSL certificate already exists"
fi

# Start nginx
exec nginx -g 'daemon off;'
