"""
Local Backup Manager
Handles automated backups of database and configuration files.
"""
import sqlite3
import shutil
import json
import logging
import tarfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class BackupManager:
    """Manage local backups of database and config"""

    def __init__(self, config: dict):
        self.enabled = config.get('enabled', False)
        self.backup_dir = Path('./data/backups')
        self.retention_days = config.get('retention_days', 30)
        self.compression = config.get('compression', True)

        # Paths to backup
        self.db_path = Path('./data/monitoring.db')
        self.config_path = Path('./config.json')

        # Create backup directory
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> Optional[Dict]:
        """
        Create backup of database and config.
        Returns backup info dict or None if failed.
        """
        if not self.enabled:
            logger.info("Backups are disabled")
            return None

        try:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            backup_name = f"backup-{timestamp}"
            backup_folder = self.backup_dir / backup_name
            backup_folder.mkdir(parents=True, exist_ok=True)

            # Backup database
            db_backup_path = backup_folder / 'monitoring.db'
            self._backup_database(db_backup_path)

            # Backup config
            config_backup_path = backup_folder / 'config.json'
            self._backup_config(config_backup_path)

            # Create metadata file
            metadata = {
                'created_at': datetime.now().isoformat(),
                'timestamp': timestamp,
                'files': {
                    'database': 'monitoring.db',
                    'config': 'config.json'
                },
                'sizes': {
                    'database': db_backup_path.stat().st_size,
                    'config': config_backup_path.stat().st_size if config_backup_path.exists() else 0
                }
            }

            metadata_path = backup_folder / 'backup.json'
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Compress if enabled
            if self.compression:
                archive_path = self._compress_backup(backup_folder)
                # Remove uncompressed folder
                shutil.rmtree(backup_folder)
                final_path = archive_path
            else:
                final_path = backup_folder

            logger.info(f"✅ Backup created: {final_path}")

            # Cleanup old backups
            self.cleanup_old_backups()

            return {
                'path': str(final_path),
                'name': final_path.name,
                'created_at': metadata['created_at'],
                'compressed': self.compression,
                'size': self._get_backup_size(final_path),
                'size_human': self._format_size(self._get_backup_size(final_path))
            }

        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            return None

    def _backup_database(self, dest_path: Path):
        """Backup SQLite database using backup API"""
        src_conn = sqlite3.connect(str(self.db_path))
        dest_conn = sqlite3.connect(str(dest_path))

        # Use SQLite backup API (safe while DB is in use)
        src_conn.backup(dest_conn)

        dest_conn.close()
        src_conn.close()

        logger.debug(f"Database backed up to: {dest_path}")

    def _backup_config(self, dest_path: Path):
        """Backup configuration file"""
        if self.config_path.exists():
            shutil.copy2(self.config_path, dest_path)
            logger.debug(f"Config backed up to: {dest_path}")
        else:
            logger.warning(f"Config file not found: {self.config_path}")

    def _compress_backup(self, backup_folder: Path) -> Path:
        """Compress backup folder to .tar.gz"""
        archive_name = f"{backup_folder.name}.tar.gz"
        archive_path = self.backup_dir / archive_name

        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(backup_folder, arcname=backup_folder.name)

        logger.debug(f"Backup compressed to: {archive_path}")
        return archive_path

    def list_backups(self) -> List[Dict]:
        """List all available backups with metadata"""
        backups = []

        # Find compressed backups
        for backup_file in sorted(self.backup_dir.glob("backup-*.tar.gz"), reverse=True):
            backups.append(self._get_backup_info(backup_file))

        # Find uncompressed backups
        for backup_folder in sorted(self.backup_dir.glob("backup-*"), reverse=True):
            if backup_folder.is_dir():
                backups.append(self._get_backup_info(backup_folder))

        return backups

    def _get_backup_info(self, path: Path) -> Dict:
        """Get backup information"""
        stat = path.stat()

        # Try to read metadata
        metadata = {}
        if path.is_dir():
            metadata_file = path / 'backup.json'
            if metadata_file.exists():
                try:
                    with open(metadata_file) as f:
                        metadata = json.load(f)
                except Exception as e:
                    logger.debug(f"Failed to read backup metadata: {e}")

        return {
            'name': path.name,
            'path': str(path),
            'size': self._get_backup_size(path),
            'size_human': self._format_size(self._get_backup_size(path)),
            'created_at': metadata.get('created_at') or datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'age_days': (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days,
            'compressed': path.suffix == '.gz',
            'metadata': metadata
        }

    def _get_backup_size(self, path: Path) -> int:
        """Get total size of backup"""
        if path.is_file():
            return path.stat().st_size
        else:
            return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def cleanup_old_backups(self):
        """Remove backups older than retention period"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        removed_count = 0

        # Check compressed backups
        for backup_file in self.backup_dir.glob("backup-*.tar.gz"):
            mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
            if mtime < cutoff_date:
                backup_file.unlink()
                removed_count += 1
                logger.info(f"Removed old backup: {backup_file.name}")

        # Check uncompressed backups
        for backup_folder in self.backup_dir.glob("backup-*"):
            if backup_folder.is_dir():
                mtime = datetime.fromtimestamp(backup_folder.stat().st_mtime)
                if mtime < cutoff_date:
                    shutil.rmtree(backup_folder)
                    removed_count += 1
                    logger.info(f"Removed old backup: {backup_folder.name}")

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old backup(s)")

    def get_backup_file_path(self, backup_name: str) -> Optional[Path]:
        """Get full path to backup file for download"""
        # Remove .tar.gz if included in name
        if backup_name.endswith('.tar.gz'):
            backup_name_base = backup_name[:-7]
        else:
            backup_name_base = backup_name

        # Try compressed first
        compressed = self.backup_dir / f"{backup_name_base}.tar.gz"
        if compressed.exists():
            return compressed

        # Try exact name
        exact = self.backup_dir / backup_name
        if exact.exists():
            return exact

        # Try uncompressed folder
        folder = self.backup_dir / backup_name_base
        if folder.exists() and folder.is_dir():
            # Need to compress on-the-fly for download
            import tempfile

            temp_archive = Path(tempfile.gettempdir()) / f"{backup_name_base}.tar.gz"
            with tarfile.open(temp_archive, 'w:gz') as tar:
                tar.add(folder, arcname=backup_name_base)

            return temp_archive

        return None

    def delete_backup(self, backup_name: str) -> bool:
        """Delete a backup"""
        backup_path = self.get_backup_file_path(backup_name)

        if not backup_path or not backup_path.exists():
            logger.warning(f"Backup not found: {backup_name}")
            return False

        try:
            if backup_path.is_file():
                backup_path.unlink()
            else:
                shutil.rmtree(backup_path)

            logger.info(f"Backup deleted: {backup_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete backup {backup_name}: {e}")
            return False

    def restore_backup(self, backup_name: str) -> Dict[str, any]:
        """
        Restore a backup by extracting database and config.
        Returns dict with status and details.

        IMPORTANT: This will OVERWRITE the current database and config!
        The application should be stopped before restoring.
        """
        backup_path = self.get_backup_file_path(backup_name)

        if not backup_path or not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_name}")

        try:
            import tempfile

            # Create temporary extraction directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Extract backup
                if backup_path.suffix == '.gz' and backup_path.stem.endswith('.tar'):
                    # Extract tar.gz with security validation
                    with tarfile.open(backup_path, 'r:gz') as tar:
                        # Security check 1: Validate uncompressed size (prevent zip bombs)
                        self._check_uncompressed_size(tar)

                        # Security check 2: Validate file contents (whitelist allowed files)
                        self._validate_backup_contents(tar)

                        # Security check 3: Safe extraction (prevent path traversal)
                        self._safe_extract_tar(tar, temp_path)

                    # Find the backup folder inside (should be backup-YYYYMMDD-HHMMSS/)
                    backup_folders = list(temp_path.glob('backup-*'))
                    if not backup_folders:
                        raise ValueError("Invalid backup archive: no backup folder found")
                    extract_folder = backup_folders[0]
                else:
                    # Already a folder
                    extract_folder = backup_path

                # Read metadata
                metadata_file = extract_folder / 'backup.json'
                metadata = {}
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)

                # Verify backup contents
                db_backup = extract_folder / 'monitoring.db'
                config_backup = extract_folder / 'config.json'

                if not db_backup.exists():
                    raise ValueError("Invalid backup: database file not found")

                # Create backup of current files before restoring
                current_backup_dir = Path(temp_dir) / 'current_backup'
                current_backup_dir.mkdir()

                if self.db_path.exists():
                    shutil.copy2(self.db_path, current_backup_dir / 'monitoring.db')
                if self.config_path.exists():
                    shutil.copy2(self.config_path, current_backup_dir / 'config.json')

                # SECURITY: Warn about database restore while app is running
                # This is a critical operation that should ideally be done with app stopped
                logger.warning("⚠️  CRITICAL: Restoring database while application is running!")
                logger.warning("⚠️  For safest restore, stop the application first.")
                logger.warning("⚠️  Current database backed up to temporary location.")

                # Validate database file before restoring
                try:
                    # Try to open the backup database to ensure it's valid SQLite
                    import sqlite3
                    conn = sqlite3.connect(db_backup)
                    cursor = conn.cursor()
                    # Check if it has the expected tables
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='targets'")
                    if not cursor.fetchone():
                        conn.close()
                        raise ValueError("Backup database is missing 'targets' table")
                    conn.close()
                    logger.info("✓ Backup database validated successfully")
                except sqlite3.Error as e:
                    raise ValueError(f"Backup database is corrupt or invalid: {e}")

                # Restore database
                shutil.copy2(db_backup, self.db_path)
                logger.info(f"Restored database from backup: {backup_name}")

                # Restore config if it exists in backup
                restored_config = False
                if config_backup.exists():
                    shutil.copy2(config_backup, self.config_path)
                    logger.info(f"Restored config from backup: {backup_name}")
                    restored_config = True

                return {
                    'success': True,
                    'backup_name': backup_name,
                    'database_restored': True,
                    'config_restored': restored_config,
                    'backup_metadata': metadata,
                    'message': 'Backup restored successfully. Please restart the application.'
                }

        except Exception as e:
            logger.error(f"Failed to restore backup {backup_name}: {e}")
            raise Exception(f"Failed to restore backup: {str(e)}")

    def import_backup(self, file_content: bytes, filename: str) -> Dict[str, any]:
        """
        Import an external backup file by saving it to the backup directory.
        Returns dict with backup info.

        Args:
            file_content: The backup file content as bytes
            filename: Original filename (should end with .tar.gz)

        Returns:
            Dictionary with backup information
        """
        # Validate filename
        if not filename.endswith('.tar.gz'):
            raise ValueError("Backup file must be a .tar.gz archive")

        # Security: validate filename doesn't contain path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            raise ValueError("Invalid filename")

        # Generate safe filename with timestamp if needed
        if not filename.startswith('backup-'):
            # Add timestamp prefix to make it unique
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            safe_filename = f"backup-{timestamp}-imported.tar.gz"
        else:
            safe_filename = filename

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Save file to backup directory
        backup_path = self.backup_dir / safe_filename

        # Check if file already exists
        if backup_path.exists():
            raise FileExistsError(f"Backup already exists: {safe_filename}")

        try:
            # Write file content
            with open(backup_path, 'wb') as f:
                f.write(file_content)

            # Security validation: Open and validate the backup
            with tarfile.open(backup_path, 'r:gz') as tar:
                # Security check 1: Validate uncompressed size (prevent zip bombs)
                self._check_uncompressed_size(tar)

                # Security check 2: Validate file contents (whitelist allowed files)
                self._validate_backup_contents(tar)

                # Security check 3: Validate paths (prevent path traversal)
                # This validates but doesn't extract - just verifies safety
                for member in tar.getmembers():
                    if member.name.startswith('/') or '..' in member.name:
                        raise ValueError(f"Unsafe path in backup: {member.name}")
                    if member.issym() or member.islnk():
                        raise ValueError(f"Symlinks not allowed in backup: {member.name}")

                # Check for required backup folder structure
                members = tar.getnames()
                has_backup_folder = any('backup-' in name for name in members)
                if not has_backup_folder:
                    backup_path.unlink()  # Remove invalid file
                    raise ValueError("Invalid backup archive: no backup folder found")

            # Get file stats
            file_stats = backup_path.stat()

            logger.info(f"Imported backup: {safe_filename} ({file_stats.st_size} bytes)")

            return {
                'success': True,
                'filename': safe_filename,
                'path': str(backup_path),
                'size': file_stats.st_size,
                'size_human': self._format_size(file_stats.st_size),
                'message': f'Backup imported successfully: {safe_filename}'
            }

        except Exception as e:
            # Clean up on error
            if backup_path.exists():
                backup_path.unlink()
            logger.error(f"Failed to import backup: {e}")
            raise Exception(f"Failed to import backup: {str(e)}")

    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    # Security validation methods
    def _check_uncompressed_size(self, tar: tarfile.TarFile, max_size: int = 500 * 1024 * 1024) -> None:
        """
        Check total uncompressed size to prevent zip bomb attacks.

        Args:
            tar: Open tarfile object
            max_size: Maximum allowed uncompressed size in bytes (default: 500MB)

        Raises:
            ValueError: If uncompressed size exceeds limit
        """
        total_size = sum(member.size for member in tar.getmembers())

        if total_size > max_size:
            raise ValueError(
                f"Backup archive too large when uncompressed: {self._format_size(total_size)} "
                f"(maximum: {self._format_size(max_size)})"
            )

        logger.info(f"Backup uncompressed size: {self._format_size(total_size)}")

    def _validate_backup_contents(self, tar: tarfile.TarFile) -> None:
        """
        Validate that backup only contains whitelisted files.

        Args:
            tar: Open tarfile object

        Raises:
            ValueError: If backup contains unexpected files
        """
        # Allowed files in backup
        allowed_files = {'monitoring.db', 'config.json', 'backup.json'}

        for member in tar.getmembers():
            # Skip directories
            if member.isdir():
                continue

            # Get basename (file name without path)
            basename = member.name.split('/')[-1]

            # Check if file is allowed
            if basename and basename not in allowed_files:
                raise ValueError(
                    f"Backup contains unexpected file: {basename}. "
                    f"Only {', '.join(allowed_files)} are allowed."
                )

        logger.info("Backup contents validated")

    def _safe_extract_tar(self, tar: tarfile.TarFile, extract_path: Path) -> None:
        """
        Safely extract tar archive with security validation.
        Prevents path traversal, symlink attacks, and absolute path exploits.

        Args:
            tar: Open tarfile object
            extract_path: Destination directory for extraction

        Raises:
            ValueError: If archive contains unsafe paths or symlinks
        """
        for member in tar.getmembers():
            # Block absolute paths (e.g., /etc/passwd)
            if member.name.startswith('/'):
                raise ValueError(
                    f"Backup contains absolute path: {member.name}. "
                    f"Only relative paths are allowed."
                )

            # Block parent directory references (e.g., ../../etc/passwd)
            if '..' in member.name:
                raise ValueError(
                    f"Backup contains parent directory reference: {member.name}. "
                    f"Path traversal is not allowed."
                )

            # Block symlinks (could point outside directory)
            if member.issym() or member.islnk():
                raise ValueError(
                    f"Backup contains symlink: {member.name}. "
                    f"Symlinks are not allowed for security."
                )

            # Additional check: ensure resolved path is within extract directory
            member_path = extract_path / member.name
            try:
                member_path.resolve().relative_to(extract_path.resolve())
            except ValueError:
                raise ValueError(
                    f"Backup contains path that resolves outside extraction directory: {member.name}"
                )

        # All members validated - safe to extract
        tar.extractall(extract_path)
        logger.info(f"Safely extracted {len(tar.getmembers())} files from backup")
