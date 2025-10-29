#!/bin/bash

# Quizzler Backend SSL Setup Script
# Usage: ./ssl-setup.sh

set -e

DOMAIN="quizzler-backend.adityatorgal.me"
EMAIL="adityatorgal581@gmail.com"

# Colors
GREEN='\033[0;32m'
BLUE='\    #         proxy_pass http://quizzler_backend;
    #         proxy_http_version 1.1;
    #         proxy_set_header Host $host;
    #         proxy_set_header X-Real-IP $remote_addr;
    #         proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;;34m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Step 1: Get SSL certificates
get_ssl_certificates() {
    log_info "Getting SSL certificates for $DOMAIN..."
    
    # Stop all services first
    docker-compose down
    
    # Start only nginx and backend for certificate validation
    docker-compose up -d backend nginx
    
    # Wait for nginx to be ready
    sleep 15
    
    # Get certificates using certbot
    docker-compose run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email $EMAIL \
        --agree-tos \
        --no-eff-email \
        --staging \
        -d $DOMAIN
    
    if [ $? -eq 0 ]; then
        log_success "SSL certificates obtained successfully (staging)"
        
        # Get production certificates
        log_info "Getting production certificates..."
        docker-compose run --rm certbot certonly \
            --webroot \
            --webroot-path=/var/www/certbot \
            --email $EMAIL \
            --agree-tos \
            --no-eff-email \
            --force-renewal \
            -d $DOMAIN
        
        if [ $? -eq 0 ]; then
            log_success "Production SSL certificates obtained"
            return 0
        else
            log_error "Failed to get production certificates"
            return 1
        fi
    else
        log_error "Failed to get SSL certificates"
        return 1
    fi
}

# Step 2: Enable HTTPS in nginx configuration
enable_https() {
    log_info "Enabling HTTPS in nginx configuration..."
    
    # Create nginx config with HTTPS enabled
    cat > nginx/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=websocket:10m rate=5r/s;

    # Upstream backend
    upstream quizzler_backend {
        server backend:8000;
    }

    # HTTP Server (redirect to HTTPS)
    server {
        listen 80;
        server_name quizzler-backend.adityatorgal.me;

        # Let's Encrypt challenge
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        # Redirect all HTTP to HTTPS
        location / {
            return 301 https://$server_name$request_uri;
        }
    }

    # HTTPS Server
    server {
        listen 443 ssl;
        http2 on;
        server_name quizzler-backend.adityatorgal.me;

        # SSL Configuration
        ssl_certificate /etc/letsencrypt/live/quizzler-backend.adityatorgal.me/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/quizzler-backend.adityatorgal.me/privkey.pem;
        
        # SSL Security
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";

        # WebSocket Routes for Real-time Features
        location /realtime/ws/ {
            limit_req zone=websocket burst=10 nodelay;
            
            proxy_pass http://quizzler_backend;
            
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-Host $server_name;
            proxy_set_header X-Forwarded-Port $server_port;
            
            # CORS Headers for WebSocket handshake
            add_header Access-Control-Allow-Origin "https://quizzler.adityatorgal.me" always;
            add_header Access-Control-Allow-Credentials true always;
            
            # WebSocket specific timeouts
            proxy_connect_timeout 7d;
            proxy_send_timeout 7d;
            proxy_read_timeout 7d;
            proxy_cache_bypass $http_upgrade;
        }

        # API Routes - Proxy all traffic to backend
        location / {
            limit_req zone=api burst=20 nodelay;
            
            proxy_pass http://quizzler_backend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # CORS Headers for frontend domain (including PATCH method)
            add_header Access-Control-Allow-Origin "https://quizzler.adityatorgal.me" always;
            add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Content-Type, Authorization, X-Requested-With, Accept, Origin" always;
            add_header Access-Control-Allow-Credentials true always;
            
            # Handle preflight OPTIONS requests
            if ($request_method = 'OPTIONS') {
                add_header Access-Control-Allow-Origin "https://quizzler.adityatorgal.me";
                add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS";
                add_header Access-Control-Allow-Headers "Content-Type, Authorization, X-Requested-With, Accept, Origin";
                add_header Access-Control-Allow-Credentials true;
                add_header Access-Control-Max-Age 86400;
                return 204;
            }
            
            # Request timeout and buffering
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
            proxy_buffering off;
        }
    }
}
EOF

    log_success "HTTPS configuration enabled"
}

# Step 3: Restart services with HTTPS
restart_with_https() {
    log_info "Restarting services with HTTPS enabled..."
    
    # Stop all services
    docker-compose down
    
    # Start all services
    docker-compose up -d
    
    # Wait for services to be ready
    sleep 15
    
    # Test HTTPS
    if curl -f -k https://$DOMAIN/realtime/health > /dev/null 2>&1; then
        log_success "HTTPS is working correctly!"
        log_info "Your backend is now available at: https://$DOMAIN"
    else
        log_error "HTTPS test failed"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting SSL setup for Quizzler Backend..."
    
    if get_ssl_certificates; then
        if enable_https; then
            if restart_with_https; then
                log_success "SSL setup completed successfully! 🚀"
                log_info "Backend URL: https://$DOMAIN"
                log_info "Health check: https://$DOMAIN/realtime/health"
                log_info "WebSocket: wss://$DOMAIN/realtime/ws/"
            else
                log_error "Failed to restart with HTTPS"
                exit 1
            fi
        else
            log_error "Failed to enable HTTPS configuration"
            exit 1
        fi
    else
        log_error "Failed to get SSL certificates"
        exit 1
    fi
}

# Run main function
main
