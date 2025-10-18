# WebStatus - Quick Start Guide

## What You've Built

A complete network monitoring system that:
- ✅ Monitors unlimited targets (ping/HTTP/HTTPS)
- ✅ Triggers GPIO relay + audio + webhook alerts
- ✅ Beautiful web dashboard with real-time updates
- ✅ Full REST API
- ✅ Works on Mac for development, Pi for production
- ✅ Zero code changes between environments

## Start on Mac (Right Now!)

```bash
cd webstatus

# Create virtual environment (use Python 3.8+)
python3.11 -m venv venv  # or python3.9, python3.10, etc.
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run it!
python main.py
```

Open [http://localhost:8000](http://localhost:8000) 🎉

## Add Your First Target

1. Click "Add Target"
2. Try monitoring:
   - **Google**: Type=`https`, Address=`google.com`
   - **Your Router**: Type=`ping`, Address=`192.168.1.1`
   - **Local Server**: Type=`http`, Address=`localhost:3000`

The dashboard updates every 3 seconds automatically!

## Test the Alerts

### Test Relay
Settings tab → Click "Test Relay" → Watch console for mock GPIO output

### Test Audio
Settings tab → Click "Test Audio" → Should hear "The system is down"

### Test Webhook
1. Get a test webhook URL from [webhook.site](https://webhook.site)
2. Settings tab → Enable webhook → Paste URL
3. Click "Test Webhook"
4. Check webhook.site for the JSON payload

## What the Output Means

```
⚠️  Development Mode - Hardware Mocked
```
Running on Mac - GPIO/relay are simulated

```
✅ Google (google.com) - UP
```
Monitoring is working!

```
❌ Server (192.168.1.100) - DOWN (3/3) - THRESHOLD REACHED!
🔴 [MOCK] GPIO Pin 17 -> HIGH
🔊 Playing audio: system_down.aiff
```
Alert triggered! (Would activate real relay on Pi)

## Deploy to Raspberry Pi

From your Mac:

```bash
# Deploy everything
./deploy.sh pi@raspberrypi.local

# SSH to Pi and start
ssh pi@raspberrypi.local
cd webstatus
source venv/bin/activate
python main.py
```

Access at: `http://<pi-ip-address>:8000`

## Wiring Your GPIO Relay (Pi Only)

```
Raspberry Pi          Relay Module
GPIO 17 ----------->  IN
5V    ----------->  VCC
GND   ----------->  GND

Relay COM & NO ----->  Your Siren/Light
```

## Next Steps

### 1. Set Up Webhook Integration

**For Slack:**
1. Create an incoming webhook in Slack
2. Put the URL in Settings → Webhook URL
3. Enable webhook
4. Now you get Slack notifications when systems go down!

**For Home Assistant:**
1. Create a webhook automation
2. Configure it to respond to WebStatus alerts
3. Trigger lights, notifications, etc.

### 2. Run as a Service (Pi)

See `README.md` for systemd service setup - makes it start on boot!

### 3. Add More Targets

- Your home server
- Router/switch
- External websites
- Internal services
- NAS devices
- Smart home hubs

### 4. Customize Check Intervals

- Fast checks: 10-30 seconds for critical systems
- Normal checks: 60 seconds (default)
- Slow checks: 300+ seconds for less critical

### 5. Tweak Failure Thresholds

- Sensitive: threshold=1 (alert on first failure)
- Balanced: threshold=3 (default, prevents false alarms)
- Patient: threshold=5+ (only alert after many failures)

## Troubleshooting

**Port 8000 already in use?**
Edit `config.json` → change `web_port` to 8001 or any free port

**Ping doesn't work on Mac?**
The app automatically falls back to TCP checks - it's fine!

**Want to monitor more than one thing?**
Just keep adding targets - no limit!

**Database getting too big?**
The app auto-cleans history older than 30 days

## Project Structure

```
webstatus/
├── main.py              # Start here!
├── config.json          # All your settings
├── monitor/             # Monitoring logic
├── alerts/              # Relay, audio, webhooks
├── api/                 # REST API
├── web/                 # Web interface
├── database/            # SQLite database
└── data/                # Your monitoring data
```

## API Examples

Check the full API docs at [http://localhost:8000/docs](http://localhost:8000/docs)

Quick examples:

```bash
# List all targets
curl http://localhost:8000/api/targets

# Get system status
curl http://localhost:8000/api/status

# Trigger manual check
curl -X POST http://localhost:8000/api/targets/{id}/check
```

## Sound Files

The app ships with AIFF files generated on Mac. For Pi, you can:
1. Keep the AIFF files (they work!)
2. Convert to WAV for smaller size
3. Record your own messages
4. Use any alert sounds you like

See `sounds/README.md` for details.

## What Makes This Special

✨ **Zero Config Changes**: Same code runs on Mac and Pi
✨ **Physical Alerts**: Actually controls real hardware
✨ **Modern Stack**: FastAPI, async, SQLite
✨ **Production Ready**: Error handling, logging, testing
✨ **Flexible Alerts**: Relay + Audio + Webhooks
✨ **Beautiful UI**: Dark mode, responsive, real-time

## Have Fun!

This is your project now. Ideas to extend it:

- Add email notifications
- Create a mobile app using the API
- Add graph visualization for response times
- Multi-user support with authentication
- SMS alerts via Twilio
- Integration with monitoring tools
- Custom alert sounds per target
- Scheduled maintenance windows
- Alert escalation (notify different people)

**Questions or issues?** Check the full README.md

---

**Now go monitor something!** 🚀📡🚨
