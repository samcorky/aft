"""Generate test backup files for manual upload testing."""
import os

def create_test_backup(size_mb, filename):
    """Create a test SQL backup file of specified size."""
    target_size = size_mb * 1024 * 1024
    
    print(f"Creating {filename} ({size_mb}MB)...", end=" ", flush=True)
    
    with open(filename, 'wb') as f:
        # Write valid SQL backup header (matches real mysqldump format)
        header = b"-- AFT Database Backup\n"
        header += b"-- Alembic Version: 008\n"
        header += b"-- Generated for manual upload testing\n\n"
        
        # Use DROP TABLE IF EXISTS like real backups do
        header += b"DROP TABLE IF EXISTS `boards`;\n"
        header += b"CREATE TABLE `boards` (id INT PRIMARY KEY, name VARCHAR(255));\n\n"
        
        header += b"DROP TABLE IF EXISTS `columns`;\n"
        header += b"CREATE TABLE `columns` (id INT PRIMARY KEY, board_id INT, name VARCHAR(255));\n\n"
        
        header += b"DROP TABLE IF EXISTS `cards`;\n"
        header += b"CREATE TABLE `cards` (id INT PRIMARY KEY, column_id INT, title VARCHAR(255));\n\n"
        
        header += b"DROP TABLE IF EXISTS `checklist_items`;\n"
        header += b"CREATE TABLE `checklist_items` (id INT PRIMARY KEY, card_id INT, text TEXT);\n\n"
        
        header += b"DROP TABLE IF EXISTS `comments`;\n"
        header += b"CREATE TABLE `comments` (id INT PRIMARY KEY, card_id INT, text TEXT);\n\n"
        
        header += b"DROP TABLE IF EXISTS `settings`;\n"
        header += b"CREATE TABLE `settings` (`key` VARCHAR(255) PRIMARY KEY, value TEXT);\n\n"
        
        header += b"DROP TABLE IF EXISTS `alembic_version`;\n"
        header += b"CREATE TABLE `alembic_version` (version_num VARCHAR(32) PRIMARY KEY);\n"
        header += b"INSERT INTO `alembic_version` VALUES ('008');\n\n"
        
        f.write(header)
        
        # Fill with comment padding to reach target size
        remaining = target_size - len(header)
        
        # Write in 1MB chunks for efficiency
        chunk_size = 1024 * 1024  # 1MB
        chunk = b"-- " + b"x" * (chunk_size - 4) + b"\n"
        
        chunks_written = 0
        while remaining > 0:
            write_size = min(len(chunk), remaining)
            f.write(chunk[:write_size])
            remaining -= write_size
            chunks_written += 1
            
            # Progress indicator every 10MB
            if chunks_written % 10 == 0:
                print(".", end="", flush=True)
    
    actual_size = os.path.getsize(filename) / (1024 * 1024)
    print(f" Done! ({actual_size:.2f}MB)")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("GENERATING TEST BACKUP FILES")
    print("="*60)
    print("\nCreating files for manual upload testing through the UI...\n")
    
    # Generate small file to verify baseline works
    create_test_backup(1, "test_backup_1mb.sql")
    
    # Generate 99MB file (should pass validation)
    create_test_backup(99, "test_backup_99mb.sql")
    
    # Generate 101MB file (should fail validation if limit is 100MB)
    create_test_backup(101, "test_backup_101mb.sql")

    # Generate 101MB file (should fail validation if limit is 100MB)
    create_test_backup(501, "test_backup_501mb.sql")
    
    print("\n" + "="*60)
    print("FILES CREATED")
    print("="*60)
    print("\nTest files created in current directory:")
    print("  • test_backup_1mb.sql   (1MB - baseline test)")
    print("  • test_backup_99mb.sql  (99MB - should pass)")
    print("  • test_backup_101mb.sql (101MB - should fail)")
    print("\nTo test:")
    print("  1. Open http://localhost/backup-restore.html")
    print("  2. Click 'Restore from Backup'")
    print("  3. Select each file and observe behavior")
    print("\nRemember to delete these files after testing!")
    print("  git rm test_backup_*.sql")
    print("="*60 + "\n")
