"""
Audio Library Manager
Manages the audio alert library with categorized sounds and metadata.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class AudioLibrary:
    """Manages audio alert library"""

    def __init__(self, sounds_dir: str = "sounds"):
        self.sounds_dir = Path(sounds_dir)
        self.library_file = self.sounds_dir / "audio_library.json"
        self.library_data = self._load_library()

    def _load_library(self) -> Dict:
        """Load audio library metadata"""
        try:
            if self.library_file.exists():
                with open(self.library_file, 'r') as f:
                    return json.load(f)
            else:
                logger.warning(f"Audio library file not found: {self.library_file}")
                return self._get_default_library()
        except Exception as e:
            logger.error(f"Failed to load audio library: {e}")
            return self._get_default_library()

    def _get_default_library(self) -> Dict:
        """Get default library structure"""
        return {
            "library_version": "1.0",
            "default_down_alert": "system_down.aiff",
            "default_up_alert": "system_up.aiff",
            "categories": {},
            "alerts": {},
            "event_type_mappings": {}
        }

    def save_library(self):
        """Save library metadata to file"""
        try:
            with open(self.library_file, 'w') as f:
                json.dump(self.library_data, f, indent=2)
            logger.info("Audio library saved successfully")
        except Exception as e:
            logger.error(f"Failed to save audio library: {e}")

    def reload_library(self):
        """Reload library data from file"""
        self.library_data = self._load_library()
        logger.info("Audio library reloaded from file")

    def get_all_alerts(self) -> Dict:
        """Get all available audio alerts"""
        return self.library_data.get("alerts", {})

    def get_alerts_by_category(self, category: str) -> Dict:
        """Get alerts filtered by category"""
        alerts = {}
        for alert_id, alert_data in self.library_data.get("alerts", {}).items():
            if alert_data.get("category") == category:
                alerts[alert_id] = alert_data
        return alerts

    def get_alerts_by_event_type(self, event_type: str) -> List[Dict]:
        """Get alerts suitable for a specific event type"""
        alerts = []
        for alert_id, alert_data in self.library_data.get("alerts", {}).items():
            if event_type in alert_data.get("event_types", []):
                alerts.append({**alert_data, "id": alert_id})
        return alerts

    def get_alert(self, alert_id: str) -> Optional[Dict]:
        """Get specific alert by ID"""
        return self.library_data.get("alerts", {}).get(alert_id)

    def _sanitize_audio_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal attacks."""
        if not filename:
            return ""

        # Get just the basename (removes directory components)
        safe_name = Path(filename).name

        # Remove any remaining path separators or traversal patterns
        safe_name = safe_name.replace('..', '').replace('/', '').replace('\\', '')

        # Validate against allowed extensions
        allowed_extensions = {'.aiff', '.wav', '.mp3', '.m4a', '.ogg'}
        if not any(safe_name.lower().endswith(ext) for ext in allowed_extensions):
            logger.warning(f"Audio filename has invalid extension: {filename[:50]}")
            return ""

        return safe_name

    def get_alert_path(self, filename: str) -> Optional[Path]:
        """Get full path to audio file with security validation."""
        # SECURITY: Sanitize filename first to prevent path traversal
        safe_filename = self._sanitize_audio_filename(filename)
        if not safe_filename:
            return None

        # Check if it's in the root sounds directory
        root_path = self.sounds_dir / safe_filename
        try:
            # Resolve to canonical path and verify it's within allowed directory
            resolved_root = root_path.resolve()
            if resolved_root.is_relative_to(self.sounds_dir.resolve()) and resolved_root.exists():
                return resolved_root
        except (ValueError, OSError):
            pass

        # Check in library subdirectories
        for category in ["beeps", "tones", "vocal", "professional"]:
            category_path = self.sounds_dir / "library" / category / safe_filename
            try:
                resolved_category = category_path.resolve()
                if resolved_category.is_relative_to(self.sounds_dir.resolve()) and resolved_category.exists():
                    return resolved_category
            except (ValueError, OSError):
                continue

        logger.warning(f"Audio file not found: {safe_filename}")
        return None

    def get_web_path(self, filename: str) -> str:
        """Get web-accessible path for audio file (relative to /sounds/ endpoint)"""
        # SECURITY: Sanitize filename first to prevent path traversal
        safe_filename = self._sanitize_audio_filename(filename)
        if not safe_filename:
            logger.warning(f"Invalid audio filename rejected: {filename[:50]}")
            # Safe fallback to default
            return self.library_data.get("default_down_alert", "system_down.aiff")

        # Check if it's in the root sounds directory
        root_path = self.sounds_dir / safe_filename
        try:
            resolved_root = root_path.resolve()
            if resolved_root.is_relative_to(self.sounds_dir.resolve()) and resolved_root.exists():
                return safe_filename
        except (ValueError, OSError):
            pass

        # Check in library subdirectories
        for category in ["beeps", "tones", "vocal", "professional"]:
            category_path = self.sounds_dir / "library" / category / safe_filename
            try:
                resolved_category = category_path.resolve()
                if resolved_category.is_relative_to(self.sounds_dir.resolve()) and resolved_category.exists():
                    return f"library/{category}/{safe_filename}"
            except (ValueError, OSError):
                continue

        # If not found, return safe default instead of potentially unsafe input
        logger.warning(f"Audio file not found for web path: {safe_filename}")
        return self.library_data.get("default_down_alert", "system_down.aiff")

    def get_default_alert(self, event_type: str) -> str:
        """Get default alert filename for an event type"""
        event_mappings = self.library_data.get("event_type_mappings", {})
        event_config = event_mappings.get(event_type, {})

        if event_type in ["threshold_reached", "alert_repeat"]:
            return event_config.get("default_alert", self.library_data.get("default_down_alert", "system_down.aiff"))
        elif event_type == "recovered":
            return event_config.get("default_alert", self.library_data.get("default_up_alert", "system_up.aiff"))
        else:
            return self.library_data.get("default_down_alert", "system_down.aiff")

    def get_default_down_alert(self) -> str:
        """Get the default down/threshold alert filename"""
        return self.library_data.get("default_down_alert", "system_down.aiff")

    def get_default_up_alert(self) -> str:
        """Get the default up/recovered alert filename"""
        return self.library_data.get("default_up_alert", "system_up.aiff")

    def add_alert(self, alert_data: Dict) -> bool:
        """Add a new alert to the library"""
        try:
            alert_id = alert_data.get("id")
            if not alert_id:
                logger.error("Alert ID is required")
                return False

            self.library_data.setdefault("alerts", {})[alert_id] = alert_data
            self.save_library()
            return True
        except Exception as e:
            logger.error(f"Failed to add alert: {e}")
            return False

    def remove_alert(self, alert_id: str) -> bool:
        """Remove an alert from the library"""
        try:
            if alert_id in self.library_data.get("alerts", {}):
                del self.library_data["alerts"][alert_id]
                self.save_library()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove alert: {e}")
            return False

    def get_categories(self) -> Dict:
        """Get all categories"""
        return self.library_data.get("categories", {})

    def scan_audio_files(self) -> List[str]:
        """Scan sounds directory for audio files not in library"""
        audio_extensions = ['.aiff', '.wav', '.mp3', '.m4a', '.ogg']
        found_files = []

        # Scan root directory
        for ext in audio_extensions:
            found_files.extend([f.name for f in self.sounds_dir.glob(f"*{ext}")])

        # Scan library subdirectories
        library_dir = self.sounds_dir / "library"
        if library_dir.exists():
            for category in library_dir.iterdir():
                if category.is_dir():
                    for ext in audio_extensions:
                        found_files.extend([f.name for f in category.glob(f"*{ext}")])

        # Filter out files already in library
        existing_files = set(alert["filename"] for alert in self.library_data.get("alerts", {}).values())
        new_files = [f for f in found_files if f not in existing_files]

        return new_files

    def get_library_stats(self) -> Dict:
        """Get library statistics"""
        alerts = self.library_data.get("alerts", {})
        categories = {}

        for alert_data in alerts.values():
            category = alert_data.get("category", "uncategorized")
            categories[category] = categories.get(category, 0) + 1

        return {
            "total_alerts": len(alerts),
            "categories": categories,
            "library_version": self.library_data.get("library_version", "1.0")
        }


# Global instance
audio_library = AudioLibrary()
