# AFT Architecture Decisions

This document captures high-level architecture decisions and the rationale behind them.

## Background Services: Daemon Threads vs. Celery

**Decision**: Use in-process daemon-thread schedulers instead of Celery.

**Rationale**:
- Current workload is periodic and predictable (backups, recurring card creation, housekeeping checks)
- No immediate need for distributed workers, queue routing, or advanced retry orchestration
- Simpler deployment and operations (no separate broker/worker stack)
- Lower maintenance overhead for a self-hosted deployment model

**When to reconsider**:
- High task volume or long-running jobs
- Need for isolated worker scaling
- Task prioritization, delayed retries, and queue-level observability requirements

**Implementation references**:
- `server/backup_scheduler.py`
- `server/card_scheduler.py`
- `server/housekeeping_scheduler.py`

## Single Container Runtime vs. Microservices

**Decision**: Keep API and schedulers in the same server runtime.

**Rationale**:
- Simpler startup and orchestration
- Shared access to Flask app context, models, and utility modules
- Fewer moving parts for small-team/self-hosted operations

**Trade-offs**:
- Service lifecycle is coupled (scheduler restarts when server restarts)
- Independent horizontal scaling of background processors is limited

**Current safeguards**:
- Scheduler initialization lock to avoid duplicate startup in multi-process/container races
- Health monitoring integrated with housekeeping checks

**Implementation references**:
- `server/app.py` (`init_backup_scheduler()`, `init_card_scheduler()`, `init_housekeeping_scheduler()`)
- `server/scheduler_lock.py`
