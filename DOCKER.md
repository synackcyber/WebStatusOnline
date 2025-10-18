# WebStatus - Docker Deployment Guide

This guide explains how to run WebStatus using Docker for easy deployment and isolation.

## Features

- **No GPIO dependencies** - Relay/GPIO support removed for Docker compatibility
- **Isolated environment** - Run without conflicting with other Python applications
- **Easy deployment** - Single command to build and run
- **Persistent data** - Database, logs, and config persisted via volumes
- **Health checks** - Automatic container health monitoring
- **Audio support** - ALSA for audio playback in container

## Quick Start

### Prerequisites

- Docker installed (version 20.10+)
- Docker Compose installed (version 1.29+)

### 1. Build and Run with Docker Compose (Recommended)

```bash
# Build and start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

The application will be available at [http://localhost:8000](http://localhost:8000)

### 2. Build and Run with Docker CLI

```bash
# Build the image
docker build -t webstatus:latest .

# Run the container
docker run -d \
  --name webstatus \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/sounds/custom:/app/sounds/custom \
  -e TZ=America/New_York \
  --restart unless-stopped \
  webstatus:latest

# View logs
docker logs -f webstatus

# Stop the container
docker stop webstatus

# Remove the container
docker rm webstatus
```

## Configuration

### Environment Variables

You can customize the container environment in [docker-compose.yml](docker-compose.yml:17-19):

```yaml
environment:
  - TZ=America/New_York  # Your timezone
  - PYTHONUNBUFFERED=1   # Immediate log output
```

### Volumes

The following directories are mounted for persistence:

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./data` | `/app/data` | SQLite database |
| `./logs` | `/app/logs` | Application logs |
| `./config.json` | `/app/config.json` | Configuration file |
| `./sounds/custom` | `/app/sounds/custom` | Custom audio files |

### Ports

By default, port 8000 is exposed. Change in [docker-compose.yml](docker-compose.yml:10-11):

```yaml
ports:
  - "8080:8000"  # Map to port 8080 on host
```

## Management Commands

### View Container Status

```bash
docker ps | grep webstatus
```

### View Logs

```bash
# All logs
docker-compose logs

# Follow logs in real-time
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100
```

### Restart Container

```bash
docker-compose restart
```

### Update Configuration

1. Edit `config.json` on the host
2. Restart the container:
   ```bash
   docker-compose restart
   ```

### Access Container Shell

```bash
# Using docker-compose
docker-compose exec webstatus /bin/bash

# Using docker CLI
docker exec -it webstatus /bin/bash
```

### Check Health Status

```bash
# View health status
docker inspect --format='{{.State.Health.Status}}' webstatus

# View health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' webstatus
```

## Migrating from Non-Docker Installation

### 1. Backup Your Data

```bash
# Backup database
cp data/monitoring.db data/monitoring.db.backup

# Backup configuration
cp config.json config.json.backup
```

### 2. Stop Existing Service

```bash
# If using run.sh
./run.sh stop

# Or kill all Python processes
killall -9 python python3
```

### 3. Remove Old Config Options

GPIO/Relay configuration is no longer used. Your existing `config.json` will be automatically cleaned up, but you can manually remove these fields if present:

- `relay_gpio_pin`
- `relay_enabled`
- `audio_loop_enabled`
- `audio_loop_interval`

### 4. Start Docker Container

```bash
docker-compose up -d
```

Your existing database and configuration will be automatically picked up via volume mounts.

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs

# Ensure no port conflicts
lsof -i:8000

# Check if old processes are running
ps aux | grep python
```

### Database Locked Errors

This usually means multiple instances are running:

```bash
# Stop all containers
docker-compose down

# Kill any background processes
killall -9 python python3

# Start fresh
docker-compose up -d
```

### Audio Not Working

Audio playback in Docker requires ALSA libraries, which are included in the image. However, Docker containers have limited access to host audio devices. For production use, consider:

1. Using webhook notifications instead of audio
2. Running natively on a device with audio output (e.g., Raspberry Pi)

### Permissions Issues

```bash
# Fix ownership of data directories
sudo chown -R $(whoami):$(whoami) data logs sounds/custom

# Ensure config is readable
chmod 644 config.json
```

### Container Health Check Failing

```bash
# Check if application is responding
curl http://localhost:8000/api/status

# View detailed health check logs
docker inspect webstatus | jq '.[0].State.Health'
```

## Production Deployment

### Using a Reverse Proxy

For production, run behind nginx or Traefik:

```yaml
# docker-compose.yml addition
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.webstatus.rule=Host(`monitor.example.com`)"
```

### Resource Limits

Add resource constraints:

```yaml
# docker-compose.yml addition
deploy:
  resources:
    limits:
      cpus: '0.5'
      memory: 512M
    reservations:
      cpus: '0.25'
      memory: 256M
```

### Automated Backups

```bash
# Create backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker exec webstatus sqlite3 /app/data/monitoring.db ".backup /app/data/backup_${DATE}.db"
```

## Benefits of Docker vs Native

| Aspect | Docker | Native |
|--------|--------|--------|
| **Isolation** | Runs in container, no conflicts | Shares system Python |
| **Dependencies** | Self-contained | Manual venv management |
| **Multiple Instances** | Easy with port mapping | Manual process management |
| **GPIO Support** | Not available | Full GPIO access |
| **Deployment** | One command | Multi-step setup |
| **Updates** | Rebuild image | Pull and restart |
| **Portability** | Works anywhere | Platform-specific |

## Limitations

1. **No GPIO/Relay Control** - Relay support removed for Docker compatibility
2. **Audio Playback** - Limited in containerized environments
3. **Host Access** - Cannot directly control host hardware

For hardware control (GPIO relays), consider running natively on a Raspberry Pi instead.

## See Also

- [README.md](README.md) - General application documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide (native installation)
- [docker-compose.yml](docker-compose.yml) - Docker Compose configuration
- [Dockerfile](Dockerfile) - Container image definition
