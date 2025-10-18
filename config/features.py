"""
Feature Flags Configuration

Centralized feature flag management for controlling feature availability
across different deployment environments (on-premise, cloud, etc.).

Environment Variables:
    ENABLE_DISCOVERY: Enable/disable network discovery feature (default: true)
                     Set to 'false' in cloud deployments where network scanning
                     may be restricted or not applicable.

Usage:
    from config.features import FeatureFlags

    if not FeatureFlags.DISCOVERY_ENABLED:
        raise HTTPException(403, "Discovery feature is disabled")
"""
import os
import logging

logger = logging.getLogger(__name__)


class FeatureFlags:
    """
    Centralized feature flags for runtime feature toggling.

    All flags default to enabled (true) for backwards compatibility.
    Flags can be disabled by setting environment variables to 'false'.
    """

    # Network Discovery Feature
    # Allows scanning subnets to discover devices on the network
    DISCOVERY_ENABLED = os.getenv('ENABLE_DISCOVERY', 'true').lower() == 'true'

    @classmethod
    def get_all_features(cls) -> dict:
        """
        Get all feature flags as a dictionary.

        Returns:
            Dictionary of feature names and their enabled status
        """
        return {
            'discoveryEnabled': cls.DISCOVERY_ENABLED,
        }

    @classmethod
    def log_feature_status(cls):
        """Log the status of all feature flags on startup."""
        features = cls.get_all_features()
        logger.info("Feature Flags Configuration:")
        for feature, enabled in features.items():
            status = "✅ ENABLED" if enabled else "🔒 DISABLED"
            logger.info(f"  {feature}: {status}")


# Log feature status when module is imported
FeatureFlags.log_feature_status()
