# PiAlert API Documentation

## Overview

PiAlert provides a REST API for external integrations to access monitoring data. Use API keys to authenticate and poll alert status for automation, webhooks, IoT devices, and custom applications.

## Authentication

All API requests require an API key passed in the `x-api-key` header.

### Generate an API Key

1. Log in to your PiAlert dashboard
2. Navigate to **Settings**
3. Scroll to **API Keys** section
4. Click **Generate New API Key**
5. Give your key a name (e.g., "Home Assistant", "Node-RED")
6. Copy the key immediately (it won't be shown again)

### Using Your API Key

Include the API key in the `x-api-key` header with every request:

```bash
curl -H "x-api-key: YOUR_API_KEY_HERE" \
  http://your-server:8000/api/v1/alert-status
```

---

## Endpoints

### Get Alert Status

**Endpoint:** `GET /api/v1/alert-status`

**Description:** Lightweight polling endpoint that returns current alert state and failing targets. Optimized for 10-30 second polling intervals.

**Authentication:** Required (API key)

**Request Example:**

```bash
curl -H "x-api-key: your-api-key-here" \
  http://localhost:8000/api/v1/alert-status
```

**Response (No Alerts):**

```json
{
  "alert": false,
  "failing_targets": [],
  "failing_count": 0,
  "timestamp": "2025-10-21T21:14:18.317325+00:00"
}
```

**Response (With Alerts):**

```json
{
  "alert": true,
  "failing_targets": [
    {
      "name": "Production Server",
      "status": "down",
      "failures": 5,
      "threshold": 3
    },
    {
      "name": "Database",
      "status": "down",
      "failures": 4,
      "threshold": 3
    }
  ],
  "failing_count": 2,
  "timestamp": "2025-10-21T21:32:15.123456+00:00"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `alert` | boolean | `true` if ANY target is currently failing (exceeds threshold), `false` if all targets are OK |
| `failing_targets` | array | List of targets currently exceeding their failure threshold |
| `failing_count` | integer | Quick count of failing targets (same as `failing_targets.length`) |
| `timestamp` | string | ISO 8601 UTC timestamp of when the status was generated |

**Failing Target Object:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name of the target |
| `status` | string | Current status (always "down" for failing targets) |
| `failures` | integer | Current consecutive failure count |
| `threshold` | integer | Number of failures required to trigger an alert |

**Error Responses:**

```json
// 401 Unauthorized - Missing API key
{
  "detail": "Missing API key in x-api-key header"
}

// 401 Unauthorized - Invalid API key
{
  "detail": "Invalid or disabled API key"
}

// 429 Too Many Requests - Rate limit exceeded (valid key)
{
  "detail": "Rate limit exceeded. Try again in 42 seconds."
}
// Headers: Retry-After: 42

// 429 Too Many Requests - Too many failed auth attempts
{
  "detail": "Too many failed authentication attempts. Try again in 60 seconds."
}
// Headers: Retry-After: 60

// 500 Internal Server Error
{
  "detail": "Unable to fetch alert status"
}
```

**Notes:**
- Targets must exceed their configured `failure_threshold` to appear in `failing_targets`
- Acknowledged alerts are excluded from the response
- Disabled targets are excluded from the response
- Response size typically <500 bytes
- **Rate limit**: 120 requests/minute per API key (see Rate Limiting section below)

---

## Integration Examples

### Raspberry Pi Relay Controller

Control a physical relay based on alert state:

```python
#!/usr/bin/env python3
import requests
import RPi.GPIO as GPIO
import time

RELAY_PIN = 17  # GPIO pin number
API_URL = "http://your-server:8000/api/v1/alert-status"
API_KEY = "your-api-key-here"
POLL_INTERVAL = 30  # seconds

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)

while True:
    try:
        response = requests.get(
            API_URL,
            headers={"x-api-key": API_KEY},
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()

            if data["alert"]:
                GPIO.output(RELAY_PIN, GPIO.HIGH)  # Turn ON
                print(f"ALERT: {data['failing_count']} targets down")
            else:
                GPIO.output(RELAY_PIN, GPIO.LOW)   # Turn OFF
                print("All systems operational")
    except Exception as e:
        print(f"Error: {e}")

    time.sleep(POLL_INTERVAL)
```

### Home Assistant

Add a REST sensor to Home Assistant:

```yaml
# configuration.yaml
rest:
  - resource: "http://your-server:8000/api/v1/alert-status"
    headers:
      x-api-key: "your-api-key-here"
    scan_interval: 30
    sensor:
      - name: "PiAlert Status"
        value_template: "{{ 'Alert' if value_json.alert else 'OK' }}"
        json_attributes:
          - failing_count
          - failing_targets
          - timestamp

binary_sensor:
  - platform: template
    sensors:
      pialert_alert:
        friendly_name: "PiAlert Alert"
        value_template: "{{ state_attr('sensor.pialert_status', 'alert') }}"
        device_class: problem
```

### Node-RED

Use the HTTP Request node:

```json
{
  "method": "GET",
  "url": "http://your-server:8000/api/v1/alert-status",
  "headers": {
    "x-api-key": "your-api-key-here"
  }
}
```

Then use a Function node to process the response:

```javascript
if (msg.payload.alert) {
    msg.payload = {
        text: `⚠️ ${msg.payload.failing_count} targets are down!`,
        targets: msg.payload.failing_targets
    };
    return msg;
}
return null; // No alert
```

### Discord/Slack Webhook

Python script to send alerts to Discord/Slack:

```python
import requests
import time

PIALERT_URL = "http://your-server:8000/api/v1/alert-status"
PIALERT_API_KEY = "your-api-key-here"
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/..."

last_alert_state = False

while True:
    response = requests.get(
        PIALERT_URL,
        headers={"x-api-key": PIALERT_API_KEY}
    )

    if response.status_code == 200:
        data = response.json()

        # Alert state changed
        if data["alert"] != last_alert_state:
            if data["alert"]:
                targets = "\n".join([
                    f"- {t['name']} ({t['failures']}/{t['threshold']} failures)"
                    for t in data["failing_targets"]
                ])
                message = f"🚨 **Alert!** {data['failing_count']} targets are down:\n{targets}"
            else:
                message = "✅ All systems recovered!"

            # Send to Discord
            requests.post(DISCORD_WEBHOOK, json={"content": message})

            last_alert_state = data["alert"]

    time.sleep(30)
```

### Bash Script

Simple bash script for cron jobs or monitoring:

```bash
#!/bin/bash

API_URL="http://your-server:8000/api/v1/alert-status"
API_KEY="your-api-key-here"

response=$(curl -s -H "x-api-key: $API_KEY" "$API_URL")
alert=$(echo "$response" | jq -r '.alert')
count=$(echo "$response" | jq -r '.failing_count')

if [ "$alert" = "true" ]; then
    echo "ALERT: $count targets are down"
    echo "$response" | jq -r '.failing_targets[] | "- \(.name): \(.failures)/\(.threshold) failures"'
    exit 1
else
    echo "OK: All systems operational"
    exit 0
fi
```

### IFTTT/Zapier Webhook

Use a webhook URL to trigger IFTTT/Zapier:

```python
import requests

PIALERT_URL = "http://your-server:8000/api/v1/alert-status"
PIALERT_API_KEY = "your-api-key-here"
IFTTT_WEBHOOK = "https://maker.ifttt.com/trigger/{event}/with/key/{key}"

response = requests.get(
    PIALERT_URL,
    headers={"x-api-key": PIALERT_API_KEY}
)

if response.status_code == 200:
    data = response.json()

    if data["alert"]:
        requests.post(IFTTT_WEBHOOK, json={
            "value1": data["failing_count"],
            "value2": ", ".join([t["name"] for t in data["failing_targets"]]),
            "value3": data["timestamp"]
        })
```

---

## Best Practices

### Polling Interval

- **Recommended:** 30 seconds
- **Minimum:** 10 seconds (avoid excessive load)
- **Maximum:** 5 minutes (for timely alerts)

### Error Handling

Always handle network errors and API failures gracefully:

```python
try:
    response = requests.get(url, headers=headers, timeout=5)
    response.raise_for_status()
    data = response.json()
except requests.exceptions.RequestException as e:
    print(f"API Error: {e}")
    # Keep last known state or use safe default
except ValueError as e:
    print(f"Invalid JSON: {e}")
```

### Security

- **Use HTTPS** in production to encrypt API keys in transit
- **Store API keys securely** (environment variables, secret managers)
- **Never commit API keys** to version control
- **Rotate keys** if compromised
- **Use unique keys** per integration (easier to revoke)

### Rate Limiting

**API endpoints are protected by rate limiting to prevent abuse:**

#### Valid API Key Limits
- **120 requests per minute** per API key
- Allows polling every 30 seconds with plenty of headroom
- Status code: `429 Too Many Requests` when exceeded
- Response includes `Retry-After` header (seconds until limit resets)

#### Failed Authentication Limits
- **10 failed authentication attempts per minute** per IP address
- Prevents brute force attacks on API keys
- Status code: `429 Too Many Requests` when exceeded
- Response includes `Retry-After` header

#### Best Practices
- **Recommended polling interval**: 30 seconds (allows 120 requests/hour)
- **Minimum polling interval**: 10 seconds (still well within limits)
- **Handle 429 responses**: Check `Retry-After` header and wait before retrying
- **Use exponential backoff** on errors
- **Cache responses** when possible to reduce request frequency

#### Rate Limit Response Example

```json
{
  "detail": "Rate limit exceeded. Try again in 42 seconds."
}
```

**Response Headers:**
- `Retry-After`: Number of seconds until rate limit resets
- `Status Code`: 429 Too Many Requests

---

## Managing API Keys

### Via Web UI

1. **List Keys:** Settings → API Keys
2. **Create Key:** Click "Generate New API Key"
3. **Disable Key:** Click the pause icon
4. **Delete Key:** Click the trash icon (cannot be undone)

### Key Metadata

Each key tracks:
- **Name:** Friendly identifier
- **Created:** When the key was generated
- **Last Used:** Most recent API call
- **Usage Count:** Total number of requests
- **Status:** Active or Disabled

---

## Troubleshooting

### "Missing API key in x-api-key header"

Make sure you're including the header:

```bash
# ✅ Correct
curl -H "x-api-key: YOUR_KEY" http://...

# ❌ Wrong
curl http://...
```

### "Invalid or disabled API key"

Check that:
1. Key is copied correctly (no extra spaces)
2. Key hasn't been deleted
3. Key is enabled (not paused)
4. You're using the full key value

### Connection Refused

- Verify PiAlert is running: `docker compose ps`
- Check the correct port (default: 8000)
- Ensure firewall allows connections
- Use correct hostname/IP address

### Empty Response

If `failing_targets` is always empty:
- Check that targets are configured in PiAlert
- Verify targets are enabled
- Ensure failure thresholds are properly set
- Targets must actually be failing to appear

---

## API Versioning

Current API version: **v1**

All endpoints are prefixed with `/api/v1/`. Future versions will use `/api/v2/`, etc.

Breaking changes will only be introduced in new major versions. The v1 API will remain stable.

---

## Support

- **GitHub Issues:** https://github.com/anthropics/claude-code/issues
- **Documentation:** https://docs.claude.com/
- **PiAlert Dashboard:** Check Settings → API Keys for usage statistics

---

## Example Use Cases

- **Physical Indicators:** LED strips, alarm sirens, status lights
- **Home Automation:** Trigger scenes, send notifications, control devices
- **CI/CD Pipelines:** Block deployments if monitoring shows issues
- **Dashboards:** Grafana, custom web dashboards
- **Mobile Apps:** iOS shortcuts, Tasker (Android)
- **Voice Assistants:** Alexa, Google Home custom skills
- **Email/SMS:** Send alerts via Twilio, SendGrid
- **Incident Management:** Auto-create PagerDuty/Opsgenie incidents

---

**API Version:** 1.0
**Last Updated:** October 2025
