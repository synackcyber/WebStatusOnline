# WebStatus

A comprehensive network monitoring system that monitors multiple targets (ping, HTTP/HTTPS) and triggers audio and webhook alerts after configurable failure thresholds.

## Features

- **Multi-Target Monitoring**: Monitor unlimited targets via ICMP ping, HTTP, and HTTPS
- **Threshold-Based Alerting**: Prevents false alarms with configurable failure thresholds
- **Audio Alerts**: Custom sound file playback with per-target alert behaviors
- **Webhook Notifications**: Universal webhook support for integration with any service
- **SMTP Email Alerts**: Send email notifications when targets go down or recover
- **Web Dashboard**: Clean, responsive web interface with real-time updates
- **REST API**: Full-featured API for automation and external integrations (Home Assistant, Node-RED, IoT devices, etc.)
- **Authentication**: Secure login system with session management
- **Alert Acknowledgment**: Silence alerts for known issues while continuing monitoring
- **Uptime Tracking**: Track uptime/downtime percentages and durations
- **Custom Audio Upload**: Upload your own alert sounds via web interface
- **Network Discovery**: Automatic subnet scanning to discover devices (configurable)
- **Platform Agnostic**: Runs on any system with Docker
- **Database Archival**: Automated cleanup of old monitoring data
- **SQLite Database**: Lightweight, persistent storage for history and statistics

## Quick Start with Docker

```bash
# Clone the repository
git clone https://github.com/synackcyber/WebStatusOnline.git
cd WebStatusOnline

# Start with Docker
./docker-quickstart.sh
```

Access the web interface at [http://localhost:8000](http://localhost:8000)

On first visit, you'll be prompted to create an admin account.

## Updating to Latest Version

To update your existing installation with the latest changes:

```bash
# Navigate to your installation directory
cd /path/to/WebStatusOnline

# Pull the latest changes from GitHub
git pull origin main

# Restart the Docker containers to apply updates
docker-compose down
docker-compose up -d

# Verify the update
docker-compose logs -f
```

**Note**: Your data, configuration, and custom sounds are preserved in mounted volumes and will not be affected by updates.

## API Access for External Integrations

PiAlert provides a REST API for external integrations. Perfect for:

- **Home Automation**: Home Assistant, Node-RED
- **IoT Devices**: Raspberry Pi relays, ESP32, Arduino
- **Notifications**: Discord bots, Slack webhooks, Telegram
- **Custom Scripts**: Python, bash, JavaScript
- **Dashboards**: Grafana, custom web apps

### Quick API Example

```bash
# 1. Generate an API key in Settings → API Keys
# 2. Poll the alert status endpoint

curl -H "x-api-key: YOUR_API_KEY" \
  http://localhost:8000/api/v1/alert-status
```

**Response:**

```json
{
  "alert": true,
  "failing_targets": [
    {"name": "Server", "status": "down", "failures": 5, "threshold": 3}
  ],
  "failing_count": 1,
  "timestamp": "2025-10-21T21:14:18.317325+00:00"
}
```

📖 **Full API documentation:** [API_DOCUMENTATION.md](API_DOCUMENTATION.md)

## Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down

# Restart
docker-compose restart
```

### Using Docker CLI

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
  --restart unless-stopped \
  webstatus:latest
```

For detailed Docker deployment instructions, see [DOCKER.md](DOCKER.md).

## Configuration

All configuration is stored in `config.json`:

```json
{
  "failure_threshold": 3,
  "check_interval": 60,
  "alert_repeat_interval": 300,
  "audio_enabled": true,
  "webhook_url": "",
  "webhook_enabled": false,
  "web_port": 8000,
  "ping_timeout": 3,
  "ping_packet_count": 3,
  "ping_min_success": 1,
  "http_timeout": 10
}
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `failure_threshold` | Number of consecutive failures before alerting | 3 |
| `check_interval` | Default seconds between checks | 60 |
| `alert_repeat_interval` | Seconds between repeat alerts | 300 |
| `audio_enabled` | Enable audio alerts | true |
| `webhook_url` | HTTP POST endpoint for webhook notifications | "" |
| `webhook_enabled` | Enable webhook notifications | false |
| `web_port` | Web server port | 8000 |
| `ping_timeout` | Timeout for ping checks (seconds) | 3 |
| `ping_packet_count` | Number of ping packets to send | 3 |
| `ping_min_success` | Minimum successful packets to consider up | 1 |
| `http_timeout` | Timeout for HTTP checks (seconds) | 10 |

Configuration can also be updated through the web interface Settings tab.

## Adding Monitoring Targets

### Via Web Interface

1. Log in to the web interface at `http://localhost:8000`
2. Click "Add Target"
3. Fill in the details:
   - **Name**: Friendly name for the target
   - **Type**: ping, http, or https
   - **Address**: IP address or hostname
   - **Check Interval**: Seconds between checks
   - **Failure Threshold**: Failures before alerting
   - **Audio Behavior**: Alert frequency (Urgent/Default/Standard/Gentle/Silent)
4. Click Save

### Via API

```bash
curl -X POST http://localhost:8000/api/targets \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production Server",
    "type": "ping",
    "address": "192.168.1.100",
    "check_interval": 60,
    "failure_threshold": 3,
    "enabled": true
  }'
```

## Key Features

### Audio Alerts

WebStatus supports custom audio alerts with per-target behavior:

- **Upload custom sounds** via web interface
- **Per-target alert frequencies**: Urgent (2s), Default (5s), Standard (10s), Gentle (30s), or Silent
- **Browser-based playback** works on any system
- **Custom audio guide**: See [CUSTOM_AUDIO_GUIDE.md](CUSTOM_AUDIO_GUIDE.md)

### Alert Acknowledgment

Acknowledge alerts for known issues:
- Silences audio alerts
- Continues monitoring and tracking downtime
- Auto-clears when target recovers
- Track how long systems have been down

### Network Discovery

Automatically discover devices on your network:
- Configurable subnet scanning
- Detect common device types
- Bulk import discovered devices
- Disable discovery in cloud environments

### Webhook Integration

Send JSON payloads to any webhook URL when alerts occur:

```json
{
  "event_type": "threshold_reached",
  "target": {
    "id": "uuid",
    "name": "Production Server"
  },
  "message": "🚨 ALERT: Production Server is DOWN",
  "timestamp": "2024-01-15T10:30:00Z",
  "failures": 3,
  "threshold": 3
}
```

**Event Types**: `threshold_reached`, `recovered`, `alert_repeat`, `test`

**Integrations**: Slack, Discord, Home Assistant, or any HTTP endpoint

### SMTP Email Alerts

Configure email notifications in the Settings tab:
- Gmail, Outlook, or any SMTP server
- Send alerts when targets go down or recover
- Test email functionality before enabling


## REST API Documentation

Once running, visit [http://localhost:8000/docs](http://localhost:8000/docs) for interactive API documentation.

### Key Endpoints

**Targets:**
- `GET /api/targets` - List all targets
- `POST /api/targets` - Create new target
- `GET /api/targets/{id}` - Get target details
- `PUT /api/targets/{id}` - Update target
- `DELETE /api/targets/{id}` - Delete target
- `POST /api/targets/{id}/check` - Manually trigger check
- `POST /api/targets/{id}/acknowledge` - Acknowledge alert

**System:**
- `GET /api/status` - Get system status
- `GET /api/config` - Get configuration
- `PUT /api/config` - Update configuration
- `POST /api/test/audio` - Test audio
- `POST /api/test/webhook` - Test webhook
- `POST /api/test/smtp` - Test email

**Discovery:**
- `POST /api/discovery/scan` - Start network scan
- `GET /api/discovery/results` - Get scan results

**Authentication:**
- `POST /api/auth/register` - Create admin account (first user only)
- `POST /api/auth/login` - Login
- `POST /api/auth/logout` - Logout

## Database Maintenance

WebStatus includes automated database archival:

```bash
# View current data age
sqlite3 data/monitoring.db "SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM check_history;"

# Preview what would be archived (dry run)
./scripts/archive_old_data.sh --dry-run

# Run archival (archives data older than 90 days)
./scripts/archive_old_data.sh

# Setup automated monthly archival
./scripts/setup_archival_cron.sh
```

For detailed maintenance guide, see [docs/DATABASE_MAINTENANCE.md](docs/DATABASE_MAINTENANCE.md).

## Service Management

Using Docker Compose:

```bash
# Start the service
docker-compose up -d

# Stop the service
docker-compose down

# Restart the service
docker-compose restart

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

## Project Structure

```
webstatus/
├── main.py                      # Application entry point
├── config.json                  # Configuration file
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Docker container definition
├── docker-compose.yml           # Docker orchestration
├── docker-quickstart.sh         # Quick start script
├── run.sh                       # Service manager
├── alerts/                      # Alert systems
│   ├── audio.py                 # Audio playback
│   ├── smtp.py                  # Email notifications
│   └── webhook.py               # Webhook notifications
├── api/                         # REST API
│   ├── routes.py                # API endpoints
│   ├── auth_routes.py           # Authentication
│   └── public_routes.py         # Public endpoints
├── auth/                        # Authentication system
│   ├── manager.py               # Auth management
│   ├── middleware.py            # Auth middleware
│   └── password.py              # Password handling
├── database/                    # Database layer
│   └── db.py                    # SQLite operations
├── monitor/                     # Monitoring logic
│   ├── manager.py               # Monitoring orchestration
│   └── models.py                # Data models
├── web/                         # Web interface
│   ├── templates/               # HTML templates
│   └── static/                  # CSS, JavaScript
├── scripts/                     # Maintenance scripts
│   ├── archive_old_data.sh      # Database archival
│   └── setup_archival_cron.sh   # Cron setup
├── sounds/                      # Audio alert files
├── data/                        # Database and backups
└── logs/                        # Application logs
```

## Requirements

- **Docker & Docker Compose**: Required for deployment (any OS)
- **Network access**: For monitoring remote targets
- **Git**: For cloning and updating the repository

## Security

- **Authentication required** for web interface
- **Session management** with secure cookies
- **Password hashing** with bcrypt
- **Rate limiting** on API endpoints
- **HTTPS recommended** for production deployments

## Troubleshooting

### Database Lock Errors
Ensure only one instance is running:
```bash
docker-compose down
# or
./run.sh stop
```

### Audio Not Playing
Audio alerts use browser-based playback. Ensure your browser allows audio and isn't muted.

### Webhook Timeout
Check webhook URL is accessible:
```bash
curl -X POST https://your-webhook-url \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

### Network Discovery Not Working
Discovery requires local network access. Disable in cloud environments by setting `ENABLE_DISCOVERY=false` in environment variables.

## License

MIT License - See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests.

## Documentation

- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [DOCKER.md](DOCKER.md) - Docker deployment details
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - **API Reference for External Integrations**
- [CUSTOM_AUDIO_GUIDE.md](CUSTOM_AUDIO_GUIDE.md) - Audio customization
- [docs/DATABASE_MAINTENANCE.md](docs/DATABASE_MAINTENANCE.md) - Database maintenance

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [httpx](https://www.python-httpx.org/) - Async HTTP client
- [aiosqlite](https://aiosqlite.omnilib.dev/) - Async SQLite wrapper

---

**Happy Monitoring!** 🚨📡
