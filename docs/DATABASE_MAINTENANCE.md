# Database Maintenance Guide

## Overview

The WebStatus monitoring system uses SQLite with a 90-day data retention policy. This guide covers automated archival, manual maintenance, and backup procedures.

## Table of Contents

1. [Data Retention Policy](#data-retention-policy)
2. [Automated Archival](#automated-archival)
3. [Manual Maintenance](#manual-maintenance)
4. [Backup and Restore](#backup-and-restore)
5. [Archive Management](#archive-management)
6. [Troubleshooting](#troubleshooting)

---

## Data Retention Policy

### Retention Periods

- **Active Database:** 90 days of check_history and alert_log data
- **Archives:** Indefinite (until manually deleted)
- **Targets:** Permanent (never auto-deleted)

### Why 90 Days?

- Provides 3 months of trend analysis
- Keeps database size manageable (< 10 MB)
- Balances performance and historical data needs
- Sufficient for identifying patterns and seasonal issues

### Data Growth Estimates

With 13 targets and 10-60 second check intervals:

| Period | Approx. Records | Database Size |
|--------|----------------|---------------|
| 7 days | ~7,000 | ~2 MB |
| 30 days | ~30,000 | ~6 MB |
| 90 days | ~90,000 | ~15 MB |
| 365 days | ~365,000 | ~60 MB |

---

## Automated Archival

### Setup Automated Archival

Run once to setup monthly archival:

```bash
cd /path/to/webstatus
./scripts/setup_archival_cron.sh
```

This creates a cron job that runs on the 1st of each month at 2:00 AM.

### What Happens During Archival

1. **Identifies old records** (> 90 days)
2. **Creates archive database** in `data/archives/`
3. **Copies old records** to archive
4. **Deletes old records** from main database
5. **Optimizes database** (VACUUM, ANALYZE)
6. **Logs results** to `logs/archival.log`

### Monitoring Archival

View archival logs:
```bash
tail -f logs/archival.log
```

Check cron job status:
```bash
crontab -l | grep archive_old_data
```

---

## Manual Maintenance

### Run Archival Manually

**Dry run (preview without changes):**
```bash
./scripts/archive_old_data.sh --dry-run
```

**Actual archival:**
```bash
./scripts/archive_old_data.sh
```

**Custom retention period:**
```bash
./scripts/archive_old_data.sh --days 30    # Archive data > 30 days
./scripts/archive_old_data.sh --days 180   # Archive data > 180 days
```

### Database Optimization

Run monthly or after large deletions:

```bash
# Stop the application
docker compose down

# Optimize database
sqlite3 data/monitoring.db "
PRAGMA wal_checkpoint(FULL);
VACUUM;
ANALYZE;
PRAGMA optimize;
"

# Restart application
docker compose up -d
```

### Check Database Health

```bash
# Integrity check
sqlite3 data/monitoring.db "PRAGMA integrity_check;"

# View database size
ls -lh data/monitoring.db

# Count records
sqlite3 data/monitoring.db "
SELECT 'targets' as table_name, COUNT(*) as rows FROM targets
UNION ALL
SELECT 'check_history', COUNT(*) FROM check_history
UNION ALL
SELECT 'alert_log', COUNT(*) FROM alert_log;
"
```

### Identify Old Data

```bash
sqlite3 data/monitoring.db -header -column "
SELECT
    MIN(timestamp) as oldest_record,
    MAX(timestamp) as newest_record,
    COUNT(*) as total_records,
    COUNT(*) FILTER (WHERE timestamp < datetime('now', '-90 days')) as records_90d_old
FROM check_history;
"
```

---

## Backup and Restore

### Automated Backups

Backups are created automatically before archival in:
```
data/monitoring.db.backup-YYYYMMDD-HHMMSS
```

### Manual Backup

```bash
# Create timestamped backup
cp data/monitoring.db data/monitoring.db.backup-$(date +%Y%m%d-%H%M%S)

# Or use sqlite3 backup command (safer during active use)
sqlite3 data/monitoring.db ".backup data/monitoring.db.backup"
```

### Restore from Backup

```bash
# Stop application
docker compose down

# Restore backup
cp data/monitoring.db.backup-YYYYMMDD-HHMMSS data/monitoring.db

# Restart application
docker compose up -d
```

### Backup Strategy Recommendations

**Frequency:**
- Daily: Automated (via cron)
- Before archival: Automatic
- Before upgrades: Manual

**Retention:**
- Keep last 7 daily backups
- Keep last 4 weekly backups
- Keep last 3 monthly backups

**Example backup cron:**
```bash
# Daily backup at 3 AM
0 3 * * * cp /path/to/webstatus/data/monitoring.db /path/to/webstatus/data/backups/daily-$(date +\%u).db

# Weekly backup on Sunday at 4 AM
0 4 * * 0 cp /path/to/webstatus/data/monitoring.db /path/to/webstatus/data/backups/weekly-$(date +\%V).db
```

---

## Archive Management

### List Archives

```bash
ls -lh data/archives/
```

### Archive Structure

Archives are SQLite databases with the same structure:

```
data/archives/archive-YYYYMMDD-HHMMSS.db
├── check_history       (archived check records)
├── alert_log          (archived alert events)
└── archive_metadata   (archive information)
```

### Query Archives

```bash
# View archive metadata
sqlite3 data/archives/archive-YYYYMMDD-HHMMSS.db "
SELECT * FROM archive_metadata;
"

# Query archived check history
sqlite3 data/archives/archive-YYYYMMDD-HHMMSS.db "
SELECT target_id, COUNT(*) as checks, MIN(timestamp), MAX(timestamp)
FROM check_history
GROUP BY target_id;
"

# Find specific target history
sqlite3 data/archives/archive-YYYYMMDD-HHMMSS.db "
SELECT * FROM check_history
WHERE target_id = 'TARGET-UUID-HERE'
ORDER BY timestamp DESC
LIMIT 100;
"
```

### Restore Data from Archive

If you need to restore archived data:

```bash
# Attach archive to main database
sqlite3 data/monitoring.db "
ATTACH DATABASE 'data/archives/archive-YYYYMMDD-HHMMSS.db' AS archive;

-- Copy specific data back
INSERT INTO main.check_history
SELECT * FROM archive.check_history
WHERE target_id = 'TARGET-UUID-HERE';

DETACH DATABASE archive;
"
```

### Delete Old Archives

After verifying you don't need old archives:

```bash
# List archives older than 1 year
find data/archives/ -name "archive-*.db" -mtime +365 -ls

# Delete archives older than 1 year
find data/archives/ -name "archive-*.db" -mtime +365 -delete
```

---

## Troubleshooting

### Archive Script Fails

**Check permissions:**
```bash
ls -la scripts/archive_old_data.sh
chmod +x scripts/archive_old_data.sh
```

**Check database lock:**
```bash
# Stop application to release lock
docker compose down

# Run archive
./scripts/archive_old_data.sh

# Restart
docker compose up -d
```

### Database Corruption

If integrity check fails:

```bash
# Stop application
docker compose down

# Backup current database
cp data/monitoring.db data/monitoring.db.corrupt

# Try to repair
sqlite3 data/monitoring.db "
PRAGMA wal_checkpoint(FULL);
REINDEX;
VACUUM;
"

# Verify
sqlite3 data/monitoring.db "PRAGMA integrity_check;"

# If still corrupt, restore from backup
cp data/monitoring.db.backup-LATEST data/monitoring.db

# Restart
docker compose up -d
```

### Large Database Size

If database grows too large:

```bash
# Check current size
ls -lh data/monitoring.db

# Check record counts
sqlite3 data/monitoring.db "
SELECT
    'check_history' as table_name,
    COUNT(*) as rows,
    COUNT(*) FILTER (WHERE timestamp < datetime('now', '-90 days')) as old_rows
FROM check_history
UNION ALL
SELECT 'alert_log', COUNT(*), COUNT(*) FILTER (WHERE timestamp < datetime('now', '-90 days'))
FROM alert_log;
"

# Archive aggressively
./scripts/archive_old_data.sh --days 30
```

### Cron Job Not Running

```bash
# Check cron is running
ps aux | grep cron

# Check cron logs (macOS)
log show --predicate 'process == "cron"' --last 1h

# Check cron logs (Linux)
grep CRON /var/log/syslog

# Test script manually
./scripts/archive_old_data.sh --dry-run
```

---

## Best Practices

### Regular Maintenance Schedule

| Task | Frequency | Command |
|------|-----------|---------|
| **Automated archival** | Monthly (automatic) | `./scripts/archive_old_data.sh` |
| **Database optimization** | Quarterly | `VACUUM; ANALYZE;` |
| **Integrity check** | Quarterly | `PRAGMA integrity_check;` |
| **Backup verification** | Monthly | Restore test backup |
| **Archive cleanup** | Yearly | Delete archives > 1 year |

### Monitoring

Monitor these metrics:

- Database size (should stay < 20 MB)
- Record counts (check_history should stay < 100K)
- Oldest record age (should be < 90 days)
- Archive count and total size
- Backup age (should be < 24 hours)

### Alerting

Consider alerts for:

- Database size > 50 MB
- Oldest record > 180 days
- Failed archival (check logs)
- No recent backup (> 48 hours)

---

## Quick Reference

```bash
# View current data age
sqlite3 data/monitoring.db "SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM check_history;"

# Preview archival
./scripts/archive_old_data.sh --dry-run

# Run archival
./scripts/archive_old_data.sh

# View logs
tail -f logs/archival.log

# List archives
ls -lh data/archives/

# Database health check
sqlite3 data/monitoring.db "PRAGMA integrity_check; PRAGMA optimize;"

# Backup now
cp data/monitoring.db data/monitoring.db.backup-$(date +%Y%m%d)
```

---

## Support

For issues or questions:
1. Check logs: `logs/archival.log`
2. Run dry-run: `./scripts/archive_old_data.sh --dry-run`
3. Review troubleshooting section above
4. Check database integrity: `PRAGMA integrity_check`
