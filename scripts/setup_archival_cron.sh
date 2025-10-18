#!/bin/bash
#
# Setup Automated Archival Cron Job
# Configures monthly archival of data older than 90 days
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ARCHIVE_SCRIPT="$SCRIPT_DIR/archive_old_data.sh"
LOG_DIR="$PROJECT_DIR/logs"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}WebStatus - Archival Cron Setup${NC}"
echo ""

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Create cron entry
CRON_COMMAND="0 2 1 * * cd $PROJECT_DIR && $ARCHIVE_SCRIPT >> $LOG_DIR/archival.log 2>&1"

echo "This script will add the following cron job:"
echo ""
echo "  Schedule: 1st of every month at 2:00 AM"
echo "  Command:  $ARCHIVE_SCRIPT"
echo "  Log:      $LOG_DIR/archival.log"
echo ""
echo "Cron entry:"
echo "  $CRON_COMMAND"
echo ""

# Check if cron entry already exists
if crontab -l 2>/dev/null | grep -q "archive_old_data.sh"; then
    echo -e "${YELLOW}WARNING: Archival cron job already exists${NC}"
    echo ""
    echo "Current archival cron jobs:"
    crontab -l 2>/dev/null | grep "archive_old_data.sh" || true
    echo ""
    read -p "Remove existing and add new entry? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        # Remove old entries
        crontab -l 2>/dev/null | grep -v "archive_old_data.sh" | crontab - || true
    else
        echo "Setup cancelled"
        exit 0
    fi
fi

# Add cron job
echo ""
read -p "Add this cron job? (yes/no): " -r
echo
if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    # Add to crontab
    (crontab -l 2>/dev/null || true; echo "$CRON_COMMAND") | crontab -
    echo -e "${GREEN}✓ Cron job added successfully${NC}"
    echo ""
    echo "The archival script will run automatically on the 1st of each month at 2 AM"
    echo "Logs will be written to: $LOG_DIR/archival.log"
    echo ""
    echo "To view current cron jobs:"
    echo "  crontab -l"
    echo ""
    echo "To remove the cron job:"
    echo "  crontab -e"
    echo "  (then delete the line containing 'archive_old_data.sh')"
else
    echo "Setup cancelled"
    exit 0
fi

echo ""
echo -e "${BLUE}Manual Commands:${NC}"
echo ""
echo "Run archival manually (dry-run):"
echo "  $ARCHIVE_SCRIPT --dry-run"
echo ""
echo "Run archival manually (actual):"
echo "  $ARCHIVE_SCRIPT"
echo ""
echo "View archival logs:"
echo "  tail -f $LOG_DIR/archival.log"
echo ""
echo "List archives:"
echo "  ls -lh $PROJECT_DIR/data/archives/"
