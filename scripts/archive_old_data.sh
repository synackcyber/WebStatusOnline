#!/bin/bash
#
# Archive Old Data Script
# Archives check_history and alert_log records older than 90 days
#
# Usage: ./scripts/archive_old_data.sh [--dry-run] [--days 90]
#

set -e

# Default configuration
RETENTION_DAYS=90
DRY_RUN=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB_PATH="$PROJECT_DIR/data/monitoring.db"
ARCHIVE_DIR="$PROJECT_DIR/data/archives"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --days)
            RETENTION_DAYS="$2"
            # Validate RETENTION_DAYS is a positive integer (security: prevents SQL injection)
            if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || [ "$RETENTION_DAYS" -lt 1 ]; then
                echo "Error: --days must be a positive integer"
                exit 1
            fi
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run         Show what would be archived without making changes"
            echo "  --days N          Archive data older than N days (default: 90)"
            echo "  --help            Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate database exists
if [ ! -f "$DB_PATH" ]; then
    log_error "Database not found: $DB_PATH"
    exit 1
fi

# Create archive directory if it doesn't exist
mkdir -p "$ARCHIVE_DIR"

# Calculate cutoff date
CUTOFF_DATE=$(date -u -v-${RETENTION_DAYS}d +"%Y-%m-%d %H:%M:%S" 2>/dev/null || date -u -d "${RETENTION_DAYS} days ago" +"%Y-%m-%d %H:%M:%S")

log_info "Archive Configuration:"
echo "  Retention Period: $RETENTION_DAYS days"
echo "  Cutoff Date: $CUTOFF_DATE"
echo "  Database: $DB_PATH"
echo "  Archive Directory: $ARCHIVE_DIR"
echo "  Dry Run: $DRY_RUN"
echo ""

# Count records to archive
log_info "Analyzing records to archive..."

# Use SQLite's datetime() for date calculation instead of string interpolation (security best practice)
CHECK_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM check_history WHERE timestamp < datetime('now', '-${RETENTION_DAYS} days');")
ALERT_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM alert_log WHERE timestamp < datetime('now', '-${RETENTION_DAYS} days');")

log_info "Found $CHECK_COUNT check_history records to archive"
log_info "Found $ALERT_COUNT alert_log records to archive"

if [ $CHECK_COUNT -eq 0 ] && [ $ALERT_COUNT -eq 0 ]; then
    log_success "No records to archive. Database is up to date."
    exit 0
fi

# Show sample of oldest records
log_info "Oldest records:"
sqlite3 -header -column "$DB_PATH" "
SELECT 'check_history' as table_name, MIN(timestamp) as oldest_record, COUNT(*) as count
FROM check_history
WHERE timestamp < datetime('now', '-${RETENTION_DAYS} days')
UNION ALL
SELECT 'alert_log', MIN(timestamp), COUNT(*)
FROM alert_log
WHERE timestamp < datetime('now', '-${RETENTION_DAYS} days');
" 2>/dev/null || log_warning "Could not fetch sample records"

echo ""

if [ "$DRY_RUN" = true ]; then
    log_warning "DRY RUN MODE - No changes will be made"
    log_info "Would archive:"
    echo "  - $CHECK_COUNT check_history records"
    echo "  - $ALERT_COUNT alert_log records"
    echo "  - Archive file: archive-${TIMESTAMP}.db"
    exit 0
fi

# Confirm before proceeding
read -p "Proceed with archival? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    log_warning "Archival cancelled by user"
    exit 0
fi

# Create archive database
ARCHIVE_DB="$ARCHIVE_DIR/archive-${TIMESTAMP}.db"
log_info "Creating archive database: $ARCHIVE_DB"

# Export old records to archive database
# Note: RETENTION_DAYS is validated as a positive integer above (security: prevents SQL injection)
sqlite3 "$DB_PATH" <<EOF
-- Attach archive database
ATTACH DATABASE '$ARCHIVE_DB' AS archive;

-- Create tables in archive database
CREATE TABLE archive.check_history (
    id INTEGER PRIMARY KEY,
    target_id TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,
    response_time REAL,
    error_message TEXT
);

CREATE TABLE archive.alert_log (
    id INTEGER PRIMARY KEY,
    target_id TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    message TEXT
);

-- Copy metadata table
CREATE TABLE archive.archive_metadata (
    created_at TEXT,
    retention_days INTEGER,
    cutoff_date TEXT,
    check_history_count INTEGER,
    alert_log_count INTEGER
);

INSERT INTO archive.archive_metadata VALUES (
    datetime('now'),
    ${RETENTION_DAYS},
    datetime('now', '-${RETENTION_DAYS} days'),
    ${CHECK_COUNT},
    ${ALERT_COUNT}
);

-- Copy old records to archive
INSERT INTO archive.check_history
SELECT * FROM main.check_history
WHERE timestamp < datetime('now', '-${RETENTION_DAYS} days');

INSERT INTO archive.alert_log
SELECT * FROM main.alert_log
WHERE timestamp < datetime('now', '-${RETENTION_DAYS} days');

-- Detach archive database
DETACH DATABASE archive;
EOF

if [ $? -eq 0 ]; then
    log_success "Archive database created successfully"
else
    log_error "Failed to create archive database"
    exit 1
fi

# Delete old records from main database
log_info "Removing archived records from main database..."

sqlite3 "$DB_PATH" <<EOF
-- Delete old records (RETENTION_DAYS is validated as positive integer)
DELETE FROM check_history WHERE timestamp < datetime('now', '-${RETENTION_DAYS} days');
DELETE FROM alert_log WHERE timestamp < datetime('now', '-${RETENTION_DAYS} days');

-- Optimize database
VACUUM;
ANALYZE;
EOF

if [ $? -eq 0 ]; then
    log_success "Archived records removed from main database"
else
    log_error "Failed to remove archived records"
    exit 1
fi

# Get final statistics
REMAINING_CHECK=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM check_history;")
REMAINING_ALERT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM alert_log;")
ARCHIVE_SIZE=$(ls -lh "$ARCHIVE_DB" | awk '{print $5}')
DB_SIZE=$(ls -lh "$DB_PATH" | awk '{print $5}')

# Summary
echo ""
log_success "Archival completed successfully!"
echo ""
echo "Summary:"
echo "  Archived:"
echo "    - $CHECK_COUNT check_history records"
echo "    - $ALERT_COUNT alert_log records"
echo "    - Archive file: $ARCHIVE_DB ($ARCHIVE_SIZE)"
echo ""
echo "  Remaining in main database:"
echo "    - $REMAINING_CHECK check_history records"
echo "    - $REMAINING_ALERT alert_log records"
echo "    - Database size: $DB_SIZE"
echo ""
log_info "Archive saved to: $ARCHIVE_DB"
