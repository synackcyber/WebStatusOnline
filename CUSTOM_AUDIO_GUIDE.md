# Custom Audio Upload Guide

## Overview

You can now upload your own custom audio files for alerts! Use any sound you want - sirens, voice recordings, music clips, etc.

## How to Upload

### Via Web Interface

1. Go to **Settings** tab
2. Scroll to **Audio Alert Settings**
3. Under **Custom Audio Files**, you'll see two upload sections:
   - **Alert Sound** - Plays when system goes down
   - **Recovery Sound** - Plays when system recovers

4. Click **"Choose File"** and select your audio file
5. Click **"Upload"**
6. Done! Your custom sound will be used immediately

### Supported Formats

✅ **WAV** - Best quality, works everywhere
✅ **MP3** - Compressed, smaller file size
✅ **AIFF** - Mac native format
✅ **OGG** - Open source format
✅ **M4A** - Apple audio format

**File Size Limit**: 10MB max per file

## Quick Interval Presets

Click the preset buttons to quickly set your loop interval:

- **Urgent (2s)** - Very frequent alerts for critical systems
- **Default (5s)** - Balanced, good for most use cases
- **Standard (10s)** - Less frequent, still noticeable
- **Gentle (30s)** - Reminder-style alerts

## Tips for Great Audio Alerts

### 1. Keep It Short
- **Ideal length**: 1-3 seconds
- Loops will repeat it frequently if enabled
- Shorter = less annoying

### 2. Make It Clear
- Clear speech or distinct sounds
- Avoid overly complex audio
- Test volume levels

### 3. Voice Recordings

Record your own voice alerts:

**On Mac:**
```bash
# Use QuickTime Player
# File → New Audio Recording → Record → Save
```

**On iPhone:**
- Use Voice Memos app
- AirDrop to Mac
- Upload via web interface

**On Android:**
- Use any voice recorder app
- Transfer file to computer
- Upload via web interface

### 4. Text-to-Speech

Generate custom TTS alerts:

**Online Services:**
- [ttsmaker.com](https://ttsmaker.com/) - Free, multiple voices
- [voicemaker.in](https://voicemaker.in/) - Professional voices
- [elevenlabs.io](https://elevenlabs.io/) - AI voices (paid)

**macOS Command:**
```bash
say "Warning! Production server is down!" -o alert.aiff
```

**Python (gTTS):**
```python
from gtts import gTTS
tts = gTTS("The system is down", lang='en')
tts.save('alert.mp3')
```

## Creative Ideas

### 🚨 Emergency Sirens
Download free sirens from [freesound.org](https://freesound.org/)
- Search: "siren", "alarm", "emergency"
- Download WAV or MP3
- Upload as alert sound

### 🎵 Music Clips
- Use your favorite song intro
- Movie quotes ("Houston, we have a problem")
- Game sound effects

### 🗣️ Personal Messages
- "Hey [Your Name], check the server!"
- "Warning! Customer database is offline!"
- "[Target name] needs attention!"

### 🐶 Fun Sounds
- Dog bark for alerts
- Cat meow for recovery
- Doorbell sound
- Any sound effect you like

## Examples

### Example 1: Custom Voice Alert
```
1. Record: "Critical alert! Production database is down!"
2. Save as MP3
3. Upload to "Alert Sound"
4. Record: "All systems nominal. Database restored."
5. Upload to "Recovery Sound"
```

### Example 2: Two-Tone Siren
```
1. Download siren.wav from freesound.org
2. Upload as alert sound
3. Upload gentle chime as recovery sound
4. Set loop to 5 seconds
```

### Example 3: Star Trek Alerts
```
1. Download "Red Alert" sound
2. Upload as alert sound
3. Download "All Clear" sound
4. Upload as recovery sound
```

## API Upload

You can also upload via API:

```bash
# Upload down sound
curl -X POST http://localhost:8000/api/upload/audio/down \
  -F "file=@/path/to/alert.mp3"

# Upload up sound
curl -X POST http://localhost:8000/api/upload/audio/up \
  -F "file=@/path/to/recovery.mp3"
```

## File Management

### Where Files Are Stored
Your uploaded files are saved in:
```
webstatus/sounds/
  ├── system_down.{ext}  # Your alert sound
  └── system_up.{ext}    # Your recovery sound
```

### Replacing Files
Just upload a new file - it will replace the old one automatically!

### Backup Your Files
To backup your custom sounds:
```bash
cp sounds/system_down.* ~/backups/
cp sounds/system_up.* ~/backups/
```

### Restore Default Sounds
Delete your custom files and regenerate defaults:
```bash
cd sounds/
rm system_down.* system_up.*
say "The system is down" -o system_down.aiff
say "System restored" -o system_up.aiff
```

## Troubleshooting

**Upload button doesn't work:**
- Make sure you clicked "Choose File" first
- Check file size is under 10MB
- Verify file format is supported

**Sound doesn't play:**
- Check "Enable Audio Alerts" is checked
- Click "Test Audio" button
- Check console logs for errors
- Try a different audio format (WAV is most compatible)

**Sound quality is poor:**
- Use higher quality source file
- Avoid heavily compressed MP3s
- WAV format gives best quality

**File too large:**
- Compress your audio
- Trim to just 1-3 seconds
- Use MP3 instead of WAV
- Use online audio compressor

## Advanced: Format Conversion

If you need to convert formats:

**Using FFmpeg (Mac):**
```bash
# Install FFmpeg
brew install ffmpeg

# Convert to WAV
ffmpeg -i input.mp3 -acodec pcm_s16le -ar 44100 output.wav

# Convert to AIFF
ffmpeg -i input.mp3 output.aiff
```

**Using Online Tools:**
- [cloudconvert.com](https://cloudconvert.com/mp3-to-wav)
- [online-audio-converter.com](https://online-audio-converter.com/)

## Best Practices

1. ✅ **Test before deploying** - Use "Test Audio" button
2. ✅ **Keep backups** - Save original files
3. ✅ **Start with short sounds** - 1-3 seconds ideal
4. ✅ **Test volume** - Not too loud or too quiet
5. ✅ **Use clear audio** - Avoid background noise
6. ✅ **Consider your environment** - Office vs home use

## Legal Note

Make sure you have the right to use any audio you upload:
- ✅ Your own recordings
- ✅ Free sound effects (check license)
- ✅ Open source audio
- ❌ Copyrighted music/sounds without permission

---

**Have fun customizing your alerts!** 🔊🎵
