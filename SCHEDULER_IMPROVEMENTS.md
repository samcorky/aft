# Scheduler Stability Improvements

## Problem Analysis

After Docker container restart on your production server (at 22:47), the scheduler threads failed to start properly:

```
INFO:backup_scheduler:Backup scheduler lock file exists, another worker is handling backups
ERROR:card_scheduler:Could not acquire card scheduler lock - another instance may be running
INFO:housekeeping_scheduler:Housekeeping scheduler already running in process 17
```

### Root Causes

1. **Stale Lock Files**: Lock files from previous container persist in `/tmp/` because:
   - `/tmp/` might be mounted as a volume or persist across container restarts
   - Lock files are not cleaned up when Gunicorn receives TERM signal
   - No cleanup on container shutdown

2. **PID Reuse**: Docker containers often reuse low PIDs (1, 15, 16, 17, 18):
   - Old lock file says PID 17 owns the lock
   - New container starts, worker gets PID 17
   - Process check `os.kill(pid, 0)` succeeds because PID exists
   - But it's a different process that doesn't own the scheduler

3. **No Health Monitoring**: No way to verify if scheduler threads are actually running after startup

4. **Gunicorn Multi-Worker Race**: With 4 workers, all try to start schedulers simultaneously:
   - Race conditions in lock file creation
   - Multiple workers creating lock files
   - Confusing log output about which worker succeeded

## Proposed Solutions

### 1. Startup Lock File Cleanup ✅

**Clean lock files on app startup before any worker tries to acquire them**

```python
# In app.py before scheduler init
def cleanup_stale_scheduler_locks():
    """Remove all scheduler lock files on application startup.
    
    This ensures clean state after container restarts where lock files
    from previous containers may persist but are no longer valid.
    """
    lock_files = [
        Path("/tmp/aft_backup_scheduler.lock"),
        Path("/tmp/aft_card_scheduler.lock"),
        Path("/tmp/aft_housekeeping_scheduler.lock"),
    ]
    
    for lock_file in lock_files:
        try:
            if lock_file.exists():
                lock_file.unlink()
                logger.info(f"Cleaned up stale lock file: {lock_file}")
        except Exception as e:
            logger.warning(f"Failed to clean lock file {lock_file}: {e}")

# Call ONCE before scheduler init
cleanup_stale_scheduler_locks()
init_backup_scheduler()
init_card_scheduler()
init_housekeeping_scheduler()
```

### 2. Enhanced Lock File with Timestamp ✅

**Add container start time to lock file to detect stale locks**

```python
# In each scheduler's lock file
{
  "pid": 17,
  "container_id": "abc123def456",  # From environment or hostname
  "start_time": "2025-12-07T22:48:03Z",
  "worker_id": 2
}
```

Check if lock is stale:
- If container ID different → stale
- If start time > 10 minutes old and process not responding → stale
- If PID doesn't exist → stale

### 3. Heartbeat System ✅

**Update lock file timestamp periodically to prove thread is alive**

```python
def _run_scheduler(self):
    """Main scheduler loop with heartbeat."""
    while self.running:
        try:
            # Update heartbeat in lock file
            self._update_heartbeat()
            
            # Do scheduler work
            self._check_and_create_cards()
            
        except Exception as e:
            logger.error(f"Error in scheduler: {e}")
        
        time.sleep(60)

def _update_heartbeat(self):
    """Update lock file with current timestamp."""
    try:
        lock_data = {
            "pid": os.getpid(),
            "last_heartbeat": datetime.now().isoformat(),
            "container_id": os.environ.get('HOSTNAME', 'unknown')
        }
        self.lock_file.write_text(json.dumps(lock_data))
    except Exception as e:
        logger.warning(f"Failed to update heartbeat: {e}")
```

Check for stale lock:
```python
def _is_lock_stale(self) -> bool:
    """Check if existing lock file is stale."""
    try:
        lock_data = json.loads(self.lock_file.read_text())
        
        # Check container ID
        current_container = os.environ.get('HOSTNAME', 'unknown')
        if lock_data.get('container_id') != current_container:
            return True  # Different container
        
        # Check heartbeat age
        last_heartbeat = datetime.fromisoformat(lock_data['last_heartbeat'])
        age = (datetime.now() - last_heartbeat).total_seconds()
        
        if age > 300:  # 5 minutes without heartbeat
            return True
        
        return False
    except Exception:
        return True  # Invalid lock file = stale
```

### 4. Health Check API Endpoint ✅

**Add endpoint to verify scheduler health**

```python
@app.route('/api/scheduler/health', methods=['GET'])
def get_scheduler_health():
    """Get health status of all schedulers.
    
    Returns:
        {
            "backup_scheduler": {
                "running": true,
                "last_run": "2025-12-07T15:10:13Z",
                "next_run": "2025-12-07T15:11:13Z",
                "lock_file_exists": true,
                "lock_file_age_seconds": 45,
                "thread_alive": true
            },
            "card_scheduler": {...},
            "housekeeping_scheduler": {...}
        }
    """
    health = {}
    
    # Backup scheduler
    try:
        from backup_scheduler import get_scheduler
        scheduler = get_scheduler()
        health['backup_scheduler'] = {
            'running': scheduler.running,
            'thread_alive': scheduler.thread.is_alive() if scheduler.thread else False,
            'last_backup': scheduler.last_backup_time.isoformat() if scheduler.last_backup_time else None,
            'lock_file_exists': scheduler.lock_file.exists(),
            'permission_error': scheduler.permission_error
        }
        
        if scheduler.lock_file.exists():
            try:
                lock_data = json.loads(scheduler.lock_file.read_text())
                last_heartbeat = datetime.fromisoformat(lock_data['last_heartbeat'])
                health['backup_scheduler']['lock_file_age_seconds'] = (
                    (datetime.now() - last_heartbeat).total_seconds()
                )
                health['backup_scheduler']['lock_pid'] = lock_data.get('pid')
            except:
                health['backup_scheduler']['lock_file_age_seconds'] = None
    except Exception as e:
        health['backup_scheduler'] = {'error': str(e)}
    
    # Similar for card and housekeeping schedulers
    # ...
    
    return jsonify(health), 200
```

### 5. Signal Handler for Graceful Shutdown ✅

**Register cleanup handler for Gunicorn worker shutdown**

```python
# In app.py
import signal
import atexit

def cleanup_schedulers():
    """Clean up scheduler resources on shutdown."""
    try:
        from backup_scheduler import get_scheduler as get_backup
        get_backup().stop()
    except:
        pass
    
    try:
        from card_scheduler import get_scheduler as get_card
        get_card().stop()
    except:
        pass
    
    try:
        from housekeeping_scheduler import stop_housekeeping_scheduler
        stop_housekeeping_scheduler()
    except:
        pass
    
    logger.info("Scheduler cleanup completed")

# Register cleanup handlers
atexit.register(cleanup_schedulers)
signal.signal(signal.SIGTERM, lambda sig, frame: cleanup_schedulers())
signal.signal(signal.SIGINT, lambda sig, frame: cleanup_schedulers())
```

### 6. Better Logging ✅

**Add detailed logging at each decision point**

```python
def start(self):
    """Start the scheduler with detailed logging."""
    logger.info(f"=== {self.__class__.__name__} Start Attempt ===")
    logger.info(f"Current PID: {os.getpid()}")
    logger.info(f"Container ID: {os.environ.get('HOSTNAME', 'unknown')}")
    logger.info(f"Lock file path: {self.lock_file}")
    
    if self.running:
        logger.warning("Scheduler already running in this instance")
        return
    
    if self.lock_file.exists():
        logger.info("Lock file exists, checking if stale...")
        if self._is_lock_stale():
            logger.info("Lock file is stale, removing...")
            self.lock_file.unlink()
        else:
            lock_data = json.loads(self.lock_file.read_text())
            logger.info(f"Lock file is active - PID: {lock_data['pid']}, "
                       f"Container: {lock_data['container_id']}, "
                       f"Last heartbeat: {lock_data['last_heartbeat']}")
            return
    
    try:
        self._acquire_lock()
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info(f"✓ Scheduler started successfully - PID: {os.getpid()}, "
                   f"Thread ID: {self.thread.ident}")
    except Exception as e:
        logger.error(f"✗ Failed to start scheduler: {e}", exc_info=True)
```

### 7. Startup Retry Logic ✅

**Retry scheduler start if initial attempt fails**

```python
def init_backup_scheduler_with_retry(max_retries=3, delay=2):
    """Initialize backup scheduler with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            from backup_scheduler import get_scheduler
            scheduler = get_scheduler()
            
            # Force cleanup of stale locks on first attempt
            if attempt == 1 and scheduler.lock_file.exists():
                logger.info("Removing any stale lock files from previous container")
                scheduler.lock_file.unlink()
            
            scheduler.start()
            
            # Verify thread actually started
            time.sleep(1)
            if scheduler.thread and scheduler.thread.is_alive():
                logger.info(f"✓ Backup scheduler started successfully on attempt {attempt}")
                return True
            else:
                logger.warning(f"Backup scheduler thread not alive after attempt {attempt}")
                
        except Exception as e:
            logger.error(f"Failed to start backup scheduler (attempt {attempt}/{max_retries}): {e}")
        
        if attempt < max_retries:
            logger.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
    
    logger.error("Failed to start backup scheduler after all retries")
    return False
```

### 8. Docker Health Check ✅

**Add health check to docker-compose.yml**

```yaml
services:
  server:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/api/scheduler/health"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s
```

## Implementation Priority

### Phase 1: Critical Fixes (Immediate)

1. ✅ **Startup lock cleanup** - Clean all lock files before any scheduler init
2. ✅ **Enhanced logging** - Add detailed logging to understand what's happening
3. ✅ **Health check endpoint** - Add `/api/scheduler/health` to monitor status

### Phase 2: Stability Improvements (This Week)

4. ✅ **Heartbeat system** - Update lock files every minute with timestamp
5. ✅ **Stale lock detection** - Check heartbeat age and container ID
6. ✅ **Signal handlers** - Clean up on SIGTERM/SIGINT

### Phase 3: Monitoring (Follow-up)

7. ✅ **Docker health check** - Add to compose.yml
8. ✅ **Startup retry logic** - Retry if initial start fails
9. ✅ **Notification on failure** - Alert if scheduler fails to start after retries

## Testing Recommendations

### Manual Testing

1. **Container Restart Test**:
   ```bash
   # On production server
   docker-compose restart server
   docker-compose logs server | grep scheduler
   # Should see: "Cleaned up stale lock file", "Scheduler started successfully"
   ```

2. **Verify Schedulers Running**:
   ```bash
   curl http://localhost:5000/api/scheduler/health | jq
   # Should show all schedulers with running: true, thread_alive: true
   ```

3. **Lock File Inspection**:
   ```bash
   docker-compose exec server cat /tmp/aft_backup_scheduler.lock
   # Should show current PID, recent heartbeat timestamp
   ```

4. **Verify Functionality**:
   - Wait for scheduled card creation (check time until next run)
   - Wait for automatic backup (every minute in your test env)
   - Check logs for version check (every hour)

### Automated Testing

Add integration test:
```python
def test_scheduler_restart_handling():
    """Test schedulers restart cleanly after simulated crash."""
    # Create stale lock files
    # Start schedulers
    # Verify they clean up stale locks and start successfully
```

## Expected Log Output After Fix

```
INFO:app:Cleaning up stale scheduler lock files
INFO:app:Cleaned up stale lock file: /tmp/aft_backup_scheduler.lock
INFO:app:Cleaned up stale lock file: /tmp/aft_card_scheduler.lock
INFO:app:Cleaned up stale lock file: /tmp/aft_housekeeping_scheduler.lock
INFO:backup_scheduler:=== BackupScheduler Start Attempt ===
INFO:backup_scheduler:Current PID: 15
INFO:backup_scheduler:Container ID: a1b2c3d4e5f6
INFO:backup_scheduler:Lock file path: /tmp/aft_backup_scheduler.lock
INFO:backup_scheduler:Lock file does not exist, acquiring...
INFO:backup_scheduler:✓ Scheduler started successfully - PID: 15, Thread ID: 140234567890
INFO:card_scheduler:=== CardScheduler Start Attempt ===
INFO:card_scheduler:Current PID: 15
INFO:card_scheduler:✓ Scheduler started successfully - PID: 15, Thread ID: 140234567891
INFO:housekeeping_scheduler:=== HousekeepingScheduler Start Attempt ===
INFO:housekeeping_scheduler:✓ Scheduler started successfully - PID: 15, Thread ID: 140234567892
INFO:backup_scheduler:Backup scheduler loop iteration starting
INFO:backup_scheduler:Heartbeat updated
INFO:card_scheduler:Card scheduler loop iteration starting
INFO:housekeeping_scheduler:Checking for updates...
```

## Configuration Recommendations

### For Production

1. **Mount /tmp/ as tmpfs** (not volume) so it clears on restart:
   ```yaml
   services:
     server:
       tmpfs:
         - /tmp
   ```

2. **Reduce Gunicorn workers** for simpler lock management:
   ```dockerfile
   CMD gunicorn --workers 2 ...  # Instead of 4
   ```

3. **Add monitoring**:
   - Alert if backup hasn't run in 5 minutes
   - Alert if card scheduler hasn't checked in 5 minutes
   - Alert if housekeeping hasn't checked in 2 hours

4. **Increase health check visibility**:
   ```bash
   # Add to cron
   */5 * * * * curl -s http://localhost:5000/api/scheduler/health | jq '.[] | select(.running == false)'
   ```

## Summary

The core issue is **stale lock files from previous container instances**. The fix requires:

1. Clean all lock files on app startup (before any worker tries to acquire)
2. Add heartbeat to lock files to detect dead schedulers
3. Improve lock staleness detection (container ID + heartbeat age)
4. Add health check endpoint for monitoring
5. Add signal handlers for graceful cleanup
6. Enhance logging for debugging

This will ensure schedulers start reliably after container restarts, regardless of restart order or PID reuse.
