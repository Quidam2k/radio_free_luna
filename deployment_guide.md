# Deployment & Production Guide

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    libsqlite3-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/music

# Set environment variables
ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:///data/ai_dj.db

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run application
CMD ["python", "main.py"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  ai-dj:
    build: .
    container_name: ai-dj-main
    ports:
      - "8080:8080"
    volumes:
      - ./music:/app/music:ro
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GENIUS_API_TOKEN=${GENIUS_API_TOKEN}
      - DATABASE_URL=postgresql://ai_dj_user:${DB_PASSWORD}@postgres:5432/ai_dj
      - MUSIC_DIRECTORIES=/app/music
      - DJ_PERSONALITY=conversational
      - KNOWLEDGE_DEPTH=deep
    depends_on:
      - postgres
      - redis
      - icecast
    restart: unless-stopped
    networks:
      - ai-dj-network

  postgres:
    image: postgres:15-alpine
    container_name: ai-dj-postgres
    environment:
      - POSTGRES_DB=ai_dj
      - POSTGRES_USER=ai_dj_user
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    restart: unless-stopped
    networks:
      - ai-dj-network

  redis:
    image: redis:7-alpine
    container_name: ai-dj-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    networks:
      - ai-dj-network

  icecast:
    image: moul/icecast
    container_name: ai-dj-icecast
    ports:
      - "8000:8000"
    environment:
      - ICECAST_SOURCE_PASSWORD=${ICECAST_PASSWORD}
      - ICECAST_ADMIN_PASSWORD=${ICECAST_ADMIN_PASSWORD}
      - ICECAST_RELAY_PASSWORD=${ICECAST_RELAY_PASSWORD}
      - ICECAST_HOSTNAME=localhost
    volumes:
      - ./icecast.xml:/etc/icecast2/icecast.xml
    restart: unless-stopped
    networks:
      - ai-dj-network

  analysis-worker:
    build: .
    container_name: ai-dj-worker
    command: ["python", "-m", "src.analysis.worker"]
    volumes:
      - ./music:/app/music:ro
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GENIUS_API_TOKEN=${GENIUS_API_TOKEN}
      - DATABASE_URL=postgresql://ai_dj_user:${DB_PASSWORD}@postgres:5432/ai_dj
      - REDIS_URL=redis://redis:6379
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    deploy:
      replicas: 2
    networks:
      - ai-dj-network

  nginx:
    image: nginx:alpine
    container_name: ai-dj-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - ai-dj
    restart: unless-stopped
    networks:
      - ai-dj-network

volumes:
  postgres_data:
  redis_data:

networks:
  ai-dj-network:
    driver: bridge
```

### .env.production

```env
# Database
DB_PASSWORD=your_secure_database_password_here

# API Keys
OPENAI_API_KEY=your_openai_api_key_here
GENIUS_API_TOKEN=your_genius_token_here

# Streaming
ICECAST_PASSWORD=your_secure_icecast_password
ICECAST_ADMIN_PASSWORD=your_admin_password
ICECAST_RELAY_PASSWORD=your_relay_password

# Security
SECRET_KEY=your_secret_key_for_jwt_tokens
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,localhost

# Performance
MAX_ANALYSIS_WORKERS=4
CACHE_SIZE_MB=512
BATCH_SIZE=100
```

## Kubernetes Deployment

### kubernetes/namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ai-dj-system
```

### kubernetes/configmap.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ai-dj-config
  namespace: ai-dj-system
data:
  DJ_PERSONALITY: "conversational"
  KNOWLEDGE_DEPTH: "deep"
  TRIVIA_FREQUENCY: "moderate"
  MAX_ANALYSIS_WORKERS: "4"
  BATCH_SIZE: "100"
  CACHE_SIZE_MB: "512"
```

### kubernetes/secrets.yaml

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ai-dj-secrets
  namespace: ai-dj-system
type: Opaque
data:
  # Base64 encoded values
  openai-api-key: <base64-encoded-openai-key>
  genius-api-token: <base64-encoded-genius-token>
  db-password: <base64-encoded-db-password>
  icecast-password: <base64-encoded-icecast-password>
```

### kubernetes/persistent-volumes.yaml

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: ai-dj-music-pv
  namespace: ai-dj-system
spec:
  capacity:
    storage: 500Gi
  accessModes:
    - ReadOnlyMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: music-storage
  hostPath:
    path: /mnt/music  # Adjust to your music storage path

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ai-dj-music-pvc
  namespace: ai-dj-system
spec:
  accessModes:
    - ReadOnlyMany
  resources:
    requests:
      storage: 500Gi
  storageClassName: music-storage

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ai-dj-data-pvc
  namespace: ai-dj-system
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 50Gi
  storageClassName: fast-ssd
```

### kubernetes/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-dj-main
  namespace: ai-dj-system
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ai-dj-main
  template:
    metadata:
      labels:
        app: ai-dj-main
    spec:
      containers:
      - name: ai-dj
        image: ai-dj:latest
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          value: "postgresql://ai_dj_user:$(DB_PASSWORD)@postgres-service:5432/ai_dj"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: ai-dj-secrets
              key: openai-api-key
        - name: GENIUS_API_TOKEN
          valueFrom:
            secretKeyRef:
              name: ai-dj-secrets
              key: genius-api-token
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ai-dj-secrets
              key: db-password
        - name: MUSIC_DIRECTORIES
          value: "/app/music"
        envFrom:
        - configMapRef:
            name: ai-dj-config
        volumeMounts:
        - name: music-storage
          mountPath: /app/music
          readOnly: true
        - name: data-storage
          mountPath: /app/data
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: music-storage
        persistentVolumeClaim:
          claimName: ai-dj-music-pvc
      - name: data-storage
        persistentVolumeClaim:
          claimName: ai-dj-data-pvc

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-dj-workers
  namespace: ai-dj-system
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-dj-worker
  template:
    metadata:
      labels:
        app: ai-dj-worker
    spec:
      containers:
      - name: ai-dj-worker
        image: ai-dj:latest
        command: ["python", "-m", "src.analysis.worker"]
        env:
        - name: DATABASE_URL
          value: "postgresql://ai_dj_user:$(DB_PASSWORD)@postgres-service:5432/ai_dj"
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: ai-dj-secrets
              key: openai-api-key
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ai-dj-secrets
              key: db-password
        envFrom:
        - configMapRef:
            name: ai-dj-config
        volumeMounts:
        - name: music-storage
          mountPath: /app/music
          readOnly: true
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
      volumes:
      - name: music-storage
        persistentVolumeClaim:
          claimName: ai-dj-music-pvc
```

### kubernetes/services.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: ai-dj-service
  namespace: ai-dj-system
spec:
  selector:
    app: ai-dj-main
  ports:
    - protocol: TCP
      port: 8080
      targetPort: 8080
  type: ClusterIP

---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: ai-dj-system
spec:
  selector:
    app: postgres
  ports:
    - protocol: TCP
      port: 5432
      targetPort: 5432
  type: ClusterIP

---
apiVersion: v1
kind: Service
metadata:
  name: redis-service
  namespace: ai-dj-system
spec:
  selector:
    app: redis
  ports:
    - protocol: TCP
      port: 6379
      targetPort: 6379
  type: ClusterIP

---
apiVersion: v1
kind: Service
metadata:
  name: icecast-service
  namespace: ai-dj-system
spec:
  selector:
    app: icecast
  ports:
    - protocol: TCP
      port: 8000
      targetPort: 8000
  type: LoadBalancer
```

## Production Configuration Files

### nginx.conf

```nginx
events {
    worker_connections 1024;
}

http {
    upstream ai_dj_backend {
        server ai-dj:8080;
    }

    upstream icecast_stream {
        server icecast:8000;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=stream:10m rate=1r/s;

    server {
        listen 80;
        server_name yourdomain.com www.yourdomain.com;
        
        # Redirect HTTP to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name yourdomain.com www.yourdomain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        # API endpoints
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://ai_dj_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # WebSocket connections
        location /ws {
            proxy_pass http://ai_dj_backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        # Audio streaming
        location /stream/ {
            limit_req zone=stream burst=5 nodelay;
            proxy_pass http://icecast_stream/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            
            # Streaming optimizations
            proxy_buffering off;
            proxy_cache off;
            tcp_nodelay on;
        }

        # Static files
        location /static/ {
            alias /app/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }

        # Health check
        location /health {
            proxy_pass http://ai_dj_backend;
            access_log off;
        }

        # Main application
        location / {
            proxy_pass http://ai_dj_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### icecast.xml

```xml
<icecast>
    <location>Earth</location>
    <admin>admin@yourdomain.com</admin>

    <limits>
        <clients>100</clients>
        <sources>10</sources>
        <queue-size>524288</queue-size>
        <client-timeout>30</client-timeout>
        <header-timeout>15</header-timeout>
        <source-timeout>10</source-timeout>
        <burst-on-connect>1</burst-on-connect>
        <burst-size>65535</burst-size>
    </limits>

    <authentication>
        <source-password>your_secure_source_password</source-password>
        <relay-password>your_secure_relay_password</relay-password>
        <admin-user>admin</admin-user>
        <admin-password>your_secure_admin_password</admin-password>
    </authentication>

    <hostname>yourdomain.com</hostname>

    <listen-socket>
        <port>8000</port>
    </listen-socket>

    <mount type="normal">
        <mount-name>/ai_dj_stream</mount-name>
        <username>source</username>
        <password>your_secure_source_password</password>
        <max-listeners>50</max-listeners>
        <dump-file>/tmp/dump-example1.ogg</dump-file>
        <burst-size>65536</burst-size>
        <fallback-mount>/silence.mp3</fallback-mount>
        <fallback-override>1</fallback-override>
        <fallback-when-full>1</fallback-when-full>
        <intro>/intro.mp3</intro>
        <hidden>0</hidden>
        <no-yp>1</no-yp>
        <authentication type="htpasswd">
            <option name="filename" value="myauth"/>
            <option name="allow_duplicate_users" value="0"/>
        </authentication>
        <on-connect>/bin/my_script.sh</on-connect>
        <on-disconnect>/bin/my_script.sh</on-disconnect>
    </mount>

    <fileserve>1</fileserve>

    <paths>
        <basedir>/usr/share/icecast2</basedir>
        <logdir>/var/log/icecast2</logdir>
        <webroot>/usr/share/icecast2/web</webroot>
        <adminroot>/usr/share/icecast2/admin</adminroot>
        <alias source="/" destination="/status.xsl"/>
    </paths>

    <logging>
        <accesslog>access.log</accesslog>
        <errorlog>error.log</errorlog>
        <loglevel>3</loglevel>
        <logsize>10000</logsize>
    </logging>

    <security>
        <chroot>0</chroot>
        <changeowner>
            <user>icecast2</user>
            <group>icecast</group>
        </changeowner>
    </security>
</icecast>
```

## Monitoring and Observability

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'ai-dj'
    static_configs:
      - targets: ['ai-dj:8080']
    metrics_path: '/metrics'
    scrape_interval: 30s

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:9121']
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "AI DJ System Monitoring",
    "panels": [
      {
        "title": "Active Sessions",
        "type": "stat",
        "targets": [
          {
            "expr": "ai_dj_active_sessions_total"
          }
        ]
      },
      {
        "title": "Tracks Analyzed",
        "type": "stat",
        "targets": [
          {
            "expr": "ai_dj_tracks_analyzed_total"
          }
        ]
      },
      {
        "title": "API Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(ai_dj_http_request_duration_seconds[5m])"
          }
        ]
      },
      {
        "title": "Stream Listeners",
        "type": "graph",
        "targets": [
          {
            "expr": "ai_dj_stream_listeners"
          }
        ]
      }
    ]
  }
}
```

### Health Check Script

```bash
#!/bin/bash
# health_check.sh

API_URL="http://localhost:8080"
STREAM_URL="http://localhost:8000"

# Check API health
api_status=$(curl -s -o /dev/null -w "%{http_code}" $API_URL/health)
if [ $api_status -ne 200 ]; then
    echo "API health check failed: $api_status"
    exit 1
fi

# Check database connection
db_status=$(curl -s $API_URL/api/library/stats | jq -r '.status // "error"')
if [ "$db_status" != "ok" ]; then
    echo "Database health check failed"
    exit 1
fi

# Check stream server
stream_status=$(curl -s -o /dev/null -w "%{http_code}" $STREAM_URL/status.xsl)
if [ $stream_status -ne 200 ]; then
    echo "Stream server health check failed: $stream_status"
    exit 1
fi

echo "All health checks passed"
exit 0
```

## Deployment Scripts

### deploy.sh

```bash
#!/bin/bash
set -e

echo "Starting AI DJ System deployment..."

# Configuration
ENVIRONMENT=${1:-production}
IMAGE_TAG=${2:-latest}
NAMESPACE="ai-dj-system"

# Build and tag image
echo "Building Docker image..."
docker build -t ai-dj:$IMAGE_TAG .

# Create namespace if it doesn't exist
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Apply configurations
echo "Applying Kubernetes configurations..."
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secrets.yaml
kubectl apply -f kubernetes/persistent-volumes.yaml
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/services.yaml

# Wait for deployment to be ready
echo "Waiting for deployment to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/ai-dj-main -n $NAMESPACE

# Verify deployment
echo "Verifying deployment..."
kubectl get pods -n $NAMESPACE
kubectl get services -n $NAMESPACE

# Run health check
echo "Running health check..."
EXTERNAL_IP=$(kubectl get service ai-dj-service -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
if [ -z "$EXTERNAL_IP" ]; then
    echo "Using port-forward for health check..."
    kubectl port-forward service/ai-dj-service 8080:8080 -n $NAMESPACE &
    PF_PID=$!
    sleep 5
    curl -f http://localhost:8080/health
    kill $PF_PID
else
    curl -f http://$EXTERNAL_IP:8080/health
fi

echo "Deployment completed successfully!"
```

### backup.sh

```bash
#!/bin/bash
set -e

# Backup script for AI DJ System
BACKUP_DIR="/backups/ai-dj"
DATE=$(date +%Y%m%d_%H%M%S)
NAMESPACE="ai-dj-system"

echo "Starting backup process..."

# Create backup directory
mkdir -p $BACKUP_DIR/$DATE

# Backup database
echo "Backing up database..."
kubectl exec deployment/postgres -n $NAMESPACE -- pg_dump -U ai_dj_user ai_dj > $BACKUP_DIR/$DATE/database.sql

# Backup configuration
echo "Backing up configuration..."
kubectl get configmap ai-dj-config -n $NAMESPACE -o yaml > $BACKUP_DIR/$DATE/configmap.yaml
kubectl get secret ai-dj-secrets -n $NAMESPACE -o yaml > $BACKUP_DIR/$DATE/secrets.yaml

# Backup persistent volume data
echo "Backing up data volume..."
kubectl exec deployment/ai-dj-main -n $NAMESPACE -- tar czf - /app/data > $BACKUP_DIR/$DATE/data.tar.gz

# Create backup archive
echo "Creating backup archive..."
cd $BACKUP_DIR
tar czf ai-dj-backup-$DATE.tar.gz $DATE/
rm -rf $DATE/

echo "Backup completed: ai-dj-backup-$DATE.tar.gz"

# Cleanup old backups (keep last 7 days)
find $BACKUP_DIR -name "ai-dj-backup-*.tar.gz" -mtime +7 -delete
```

### Performance Tuning

```bash
#!/bin/bash
# performance_tuning.sh

echo "Applying performance optimizations..."

# Database optimizations
kubectl exec deployment/postgres -n ai-dj-system -- psql -U ai_dj_user -d ai_dj -c "
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tracks_themes ON track_analysis USING gin((themes::jsonb));
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tracks_artist_title ON tracks(artist, title);
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_connections_strength ON track_connections(strength DESC);
    VACUUM ANALYZE;
"

# Redis optimizations
kubectl exec deployment/redis -n ai-dj-system -- redis-cli CONFIG SET maxmemory 256mb
kubectl exec deployment/redis -n ai-dj-system -- redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Application cache warming
echo "Warming application caches..."
curl -X POST http://ai-dj-service:8080/api/admin/warm-cache

echo "Performance optimizations applied!"
```

This comprehensive deployment guide covers everything needed to run the AI DJ system in production, from local Docker development to full Kubernetes deployment with monitoring, backups, and performance optimization.