#!/bin/bash

# ── Config ────────────────────────────────────────────────
DB_PATH="/opt/hotelsrikrishna/hotelsrikrishna.db"
BUCKET="s3://hotelsrikrishna-db-backup"
BACKUP_DIR="/opt/hotelsrikrishna/backups"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/hotelsrikrishna_$DATE.db"
LOG_FILE="/opt/hotelsrikrishna/backup.log"
KEEP_DAYS=30  # local backups older than this will be deleted

# ── Create backup dir if not exists ───────────────────────
mkdir -p "$BACKUP_DIR"

echo "[$DATE] Starting backup..." >> "$LOG_FILE"

# ── Copy DB to backup folder ──────────────────────────────
cp "$DB_PATH" "$BACKUP_FILE"

if [ $? -ne 0 ]; then
    echo "[$DATE] ERROR: Failed to copy DB file" >> "$LOG_FILE"
    exit 1
fi

echo "[$DATE] DB copied to $BACKUP_FILE" >> "$LOG_FILE"

# ── Upload to S3 ──────────────────────────────────────────
aws s3 cp "$BACKUP_FILE" "$BUCKET/daily/$DATE/hotelsrikrishna.db" >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "[$DATE] ERROR: S3 upload failed" >> "$LOG_FILE"
    exit 1
fi

echo "[$DATE] Uploaded to S3 successfully" >> "$LOG_FILE"

# ── Clean up local backups older than 30 days ─────────────
find "$BACKUP_DIR" -name "*.db" -mtime +$KEEP_DAYS -delete
echo "[$DATE] Old local backups cleaned up" >> "$LOG_FILE"

echo "[$DATE] Backup completed successfully" >> "$LOG_FILE"
echo "─────────────────────────────────────" >> "$LOG_FILE"
