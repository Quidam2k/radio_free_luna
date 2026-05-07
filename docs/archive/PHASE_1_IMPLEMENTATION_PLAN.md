# Phase 1 Implementation Plan: Critical Production Fixes

**Duration**: 1-2 weeks of focused development
**Goal**: Make system production-ready by fixing 4 critical + 5 high-priority issues
**Status**: Ready for execution

---

## Quick Overview

Phase 1 focuses on fixing issues that could cause:
- **Production crashes** (global state race conditions)
- **Security breaches** (hardcoded credentials)
- **Resource exhaustion** (connection leaks, unmanaged connections)
- **DOS vulnerabilities** (missing input validation)
- **Data loss** (incomplete shutdown)

These fixes are **prerequisites** before any deployment.

---

## Detailed Task Breakdown

### TASK GROUP 1: Security & Configuration (2-3 days)

#### Task 1.1: Remove Hardcoded Credentials

**Issue**: Default password 'hackme', test API keys in code
**Files Affected**:
- `src/core/config.py`
- `src/streaming/audio_server.py`
- `src/voice/tts_config.py`

**Subtasks**:

1.1.1 **Update config.py with Pydantic validation**
- Replace all string-only config with typed Pydantic BaseSettings
- Add validators for all sensitive fields
- Remove all default values for required fields
- Make .env file mandatory for production

```python
# Key changes:
- from pydantic import BaseSettings, validator, Field
- Add @validator for each sensitive field
- Require ICECAST_PASSWORD to be set (no default)
- Require OPENAI_API_KEY to be set (no default)
- Add password strength validation (min 12 chars, uppercase, digits)
```

**Acceptance Criteria**:
- [ ] All sensitive config fields validated
- [ ] System fails to start if required env vars missing
- [ ] Password strength enforced
- [ ] No hardcoded defaults for production values

**Estimated Time**: 3-4 hours
**Files to Create/Modify**:
- Modify: `src/core/config.py` (~150 lines change)

---

1.1.2 **Fix audio_server.py default password**
- Replace `'hackme'` default with required config parameter
- Validate on startup

```python
# Change from:
password=getattr(self, 'password', 'hackme')

# To:
if not self.password:
    raise ValueError("Icecast password must be configured")
```

**Acceptance Criteria**:
- [ ] No 'hackme' default anywhere
- [ ] Startup fails if password not configured
- [ ] Test confirms startup fails without valid password

**Estimated Time**: 1-2 hours
**Files to Modify**:
- Modify: `src/streaming/audio_server.py` (~10 lines)

---

1.1.3 **Fix TTS config placeholder**
- Remove 'dummy_key' from tts_config.py
- Make API key optional with graceful fallback (already implemented)

```python
# Document that TTS is optional
# Ensure graceful degradation when key not provided
```

**Acceptance Criteria**:
- [ ] No 'dummy_key' values in code
- [ ] System starts without TTS key (with warning)
- [ ] System uses TTS when key provided

**Estimated Time**: 1 hour
**Files to Modify**:
- Modify: `src/voice/tts_config.py` (~5 lines)

---

**Subtask Summary**:
- **Total Time**: ~6-7 hours
- **Testing**: Unit test for config validation, startup test
- **Risk**: Low - configuration changes only, backward compatible
- **Dependencies**: None

---

### TASK GROUP 2: Global State & Thread Safety (2-3 days)

#### Task 2.1: Fix Global State Race Conditions

**Issue**: Mutable `app_instance` without synchronization
**Files Affected**:
- `src/main.py` (primary)
- `launch_radio_free_luna.py` (uses global)

**Subtasks**:

2.1.1 **Add thread-safe global state management**
- Implement lock for app_instance access
- Update create_app() to use lock
- Update signal handler to use lock

```python
# Key changes:
import threading
_app_lock = threading.Lock()

# Create app safely
with _app_lock:
    if app_instance is None:
        app_instance = RadioFreeLuna()

# Access app safely in signal handler
```

**Acceptance Criteria**:
- [ ] Lock protects app_instance access
- [ ] create_app() is thread-safe
- [ ] Signal handler uses lock
- [ ] Concurrency test passes (multiple tasks accessing app)

**Estimated Time**: 4-5 hours
**Files to Modify**:
- Modify: `src/main.py` (~20 lines added)
- Modify: `launch_radio_free_luna.py` (~5 lines)

---

2.1.2 **Fix signal handler to not exit immediately**
- Schedule shutdown task
- Wait for completion before exiting
- Handle case where no event loop

```python
# Key changes:
def handle_shutdown(signum, frame):
    logger.info(f"Received signal {signum}")
    with _app_lock:
        if app_instance:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(app_instance.shutdown())
            except RuntimeError:
                pass
    # Don't exit immediately - let uvicorn finish
```

**Acceptance Criteria**:
- [ ] Signal handler doesn't exit immediately
- [ ] Graceful shutdown completes before exit
- [ ] No orphaned connections
- [ ] Manual test: Kill with Ctrl+C, verify clean shutdown

**Estimated Time**: 2-3 hours
**Files to Modify**:
- Modify: `launch_radio_free_luna.py` (~10 lines)

---

**Subtask Summary**:
- **Total Time**: ~6-8 hours
- **Testing**: Concurrency test, signal handling test
- **Risk**: Medium - touches critical startup/shutdown path
- **Dependencies**: None, but should be done early

---

#### Task 2.2: Fix Resource Leaks in TTS Client

**Issue**: Unclosed aiohttp sessions, violates context manager pattern
**Files Affected**:
- `src/voice/tts_client.py`

**Subtasks**:

2.2.1 **Enforce context manager pattern**
- Add check that client initialized via context manager
- Prevent creating sessions outside context manager
- Add clear error messages

```python
# Key changes:
async def synthesize_speech(self, text, voice_settings=None):
    if not self.session:
        logger.error("TTS client not initialized via context manager")
        logger.error("Correct usage: async with TTSWebUIClient(...) as client:")
        return None
    # Use existing session
```

**Acceptance Criteria**:
- [ ] Error message clear if not using context manager
- [ ] Session never created outside __aenter__
- [ ] No resource leaks in any code path
- [ ] Integration test: Create multiple TTS instances, verify cleanup

**Estimated Time**: 2-3 hours
**Files to Modify**:
- Modify: `src/voice/tts_client.py` (~15 lines)

---

2.2.2 **Add resource cleanup tests**
- Test that sessions are properly closed
- Test exception handling doesn't leak resources
- Test multiple instance lifecycle

```python
# Test file: tests/test_tts_resources.py
@pytest.mark.asyncio
async def test_tts_client_cleanup():
    async with TTSWebUIClient(config) as client:
        # Use client
        pass
    # Verify session closed

@pytest.mark.asyncio
async def test_tts_client_exception_cleanup():
    # Verify cleanup on exception
```

**Acceptance Criteria**:
- [ ] Test file created with resource tests
- [ ] All tests pass
- [ ] No resource warnings from event loop

**Estimated Time**: 2-3 hours
**Files to Create**:
- Create: `tests/test_tts_resources.py` (new, ~50 lines)

---

**Subtask Summary**:
- **Total Time**: ~4-6 hours
- **Testing**: Resource cleanup tests, integration tests
- **Risk**: Low - clarifies existing patterns
- **Dependencies**: None

---

### TASK GROUP 3: Database & Connection Management (2-3 days)

#### Task 3.1: Implement Connection Pooling

**Issue**: Unbounded database connections, no pooling configuration
**Files Affected**:
- `src/core/database.py`
- `src/dj/session_manager.py`
- `src/core/file_monitor.py`

**Subtasks**:

3.1.1 **Add SQLAlchemy connection pooling configuration**
- Configure QueuePool with appropriate settings
- Set pool_size, max_overflow, recycle
- Add pool pre-ping for stale connection detection

```python
# Key changes in database.py:
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,           # Keep 5 connections in pool
    max_overflow=10,       # Allow 10 additional connections
    pool_pre_ping=True,    # Test connections before use
    pool_recycle=3600,     # Recycle after 1 hour
    echo=False
)
```

**Acceptance Criteria**:
- [ ] Pool configuration applied to engine
- [ ] Pre-ping enabled to detect stale connections
- [ ] Stale connections recycled after 1 hour
- [ ] Load test passes (verify pool doesn't exhaust)

**Estimated Time**: 3-4 hours
**Files to Modify**:
- Modify: `src/core/database.py` (~20 lines)

---

3.1.2 **Create context manager for session management**
- Replace ad-hoc get_db() calls with context manager
- Ensure proper transaction handling
- Guarantee cleanup on exception

```python
# Key addition to database.py:
@contextmanager
def get_db_context():
    """Context manager for database sessions"""
    session = db_manager.get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Acceptance Criteria**:
- [ ] Context manager implemented
- [ ] Transaction committed on success
- [ ] Transaction rolled back on exception
- [ ] Session always closed
- [ ] All existing db calls updated to use context manager

**Estimated Time**: 4-5 hours
**Files to Modify**:
- Modify: `src/core/database.py` (~30 lines)
- Modify: `src/dj/session_manager.py` (~20 lines)
- Modify: `src/core/file_monitor.py` (~15 lines)

---

3.1.3 **Load test database connections**
- Create test that simulates concurrent requests
- Verify pool doesn't exhaust
- Verify connections recycle properly

```python
# Test file: tests/test_db_connection_pool.py
@pytest.mark.asyncio
async def test_concurrent_db_connections():
    # Simulate 20 concurrent requests
    # Verify pool doesn't exceed max_overflow
```

**Acceptance Criteria**:
- [ ] Concurrency test created
- [ ] 20 concurrent connections don't cause "too many connections"
- [ ] Performance acceptable (response time < 1s)

**Estimated Time**: 3-4 hours
**Files to Create**:
- Create: `tests/test_db_connection_pool.py` (~50 lines)

---

**Subtask Summary**:
- **Total Time**: ~10-13 hours
- **Testing**: Connection pool load test, concurrency test
- **Risk**: Medium - database changes, needs careful testing
- **Dependencies**: None

---

#### Task 3.2: Fix Unsafe Object Serialization

**Issue**: Using __dict__ directly, crashes with non-serializable types
**Files Affected**:
- `src/dj/session_manager.py`

**Subtasks**:

3.2.1 **Create safe serialization utility**
- Handle datetime, Decimal, and other non-JSON types
- Recursive serialization for nested objects
- Comprehensive type support

```python
# New file: src/utils/serialization.py
def safe_json_serialize(obj):
    """Safely serialize objects to JSON-compatible dict"""
    # Handle datetime, Decimal, complex types
    # Recursive for nested structures
```

**Acceptance Criteria**:
- [ ] Utility handles datetime objects
- [ ] Utility handles Decimal objects
- [ ] Utility handles nested objects
- [ ] Unit tests for all types

**Estimated Time**: 3-4 hours
**Files to Create**:
- Create: `src/utils/serialization.py` (~80 lines)
- Create: `tests/test_serialization.py` (~60 lines)

---

3.2.2 **Update session_manager to use safe serialization**
- Replace inline __dict__ access with utility
- Update all context serialization calls
- Simplify code

```python
# Before (in session_manager.py):
temporal_context=json.dumps(context.get("temporal", {}).__dict__ if hasattr(...

# After:
temporal_context=json.dumps(safe_json_serialize(context.get("temporal")))
```

**Acceptance Criteria**:
- [ ] All __dict__ access removed
- [ ] All serialization uses safe utility
- [ ] Unit tests pass
- [ ] Integration test: Create session with complex context

**Estimated Time**: 2-3 hours
**Files to Modify**:
- Modify: `src/dj/session_manager.py` (~15 lines)

---

**Subtask Summary**:
- **Total Time**: ~5-7 hours
- **Testing**: Unit tests for serialization, integration test
- **Risk**: Low - utility function, isolated changes
- **Dependencies**: None

---

### TASK GROUP 4: Input Validation & API Hardening (2-3 days)

#### Task 4.1: Add Input Validation with Pydantic

**Issue**: No validation on API endpoints, DOS vulnerability, data corruption
**Files Affected**:
- `src/main.py` (all endpoint definitions)

**Subtasks**:

4.1.1 **Create Pydantic models for all request types**
- SessionRequest (theme, duration_minutes)
- TestVoiceRequest (text)
- CommentaryRequest (text_type)
- Any other endpoints

```python
# New file or add to existing: models/requests.py
from pydantic import BaseModel, validator, Field

class SessionRequest(BaseModel):
    theme: str = Field(..., min_length=1, max_length=50)
    duration_minutes: int = Field(..., ge=5, le=480)

    @validator('theme')
    def validate_theme(cls, v):
        if not v.isalnum() and v != "_":
            raise ValueError("Theme must be alphanumeric")
        return v

class TestVoiceRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
```

**Acceptance Criteria**:
- [ ] All request types have Pydantic models
- [ ] Validators enforce constraints
- [ ] Models document constraints (min/max length, allowed values)
- [ ] Unit tests for each model

**Estimated Time**: 4-5 hours
**Files to Create/Modify**:
- Create: `src/models/requests.py` (~100 lines)
- Create: `tests/test_request_models.py` (~80 lines)

---

4.1.2 **Update all endpoints to use Pydantic models**
- Replace string parameters with request models
- Update endpoint signatures
- Update docstrings

```python
# Before:
@app.post("/api/test-voice")
async def test_voice(text: str = "default"):
    pass

# After:
@app.post("/api/test-voice")
async def test_voice(request: TestVoiceRequest):
    text = request.text
    pass
```

**Acceptance Criteria**:
- [ ] All endpoints updated
- [ ] FastAPI validates automatically
- [ ] Invalid requests return 422 with clear error
- [ ] API tests still pass

**Estimated Time**: 3-4 hours
**Files to Modify**:
- Modify: `src/main.py` (~40 lines)

---

4.1.3 **Add rate limiting to expensive endpoints**
- Install slowapi dependency
- Apply rate limits to TTS, session creation, commentary
- Document limits

```python
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/test-voice")
@limiter.limit("5/minute")
async def test_voice(request: TestVoiceRequest):
    pass
```

**Acceptance Criteria**:
- [ ] Rate limiting installed and configured
- [ ] Test-voice limited to 5/minute
- [ ] Session creation limited to 10/minute
- [ ] Commentary limited to 10/minute
- [ ] Test: Verify 429 error on limit exceeded

**Estimated Time**: 2-3 hours
**Files to Modify**:
- Modify: `src/main.py` (~15 lines for rate limiting setup)

---

**Subtask Summary**:
- **Total Time**: ~9-12 hours
- **Testing**: Unit tests for models, integration tests for endpoints
- **Risk**: Low - FastAPI handles validation automatically
- **Dependencies**: Need to install slowapi

---

#### Task 4.2: Fix Database Query Issues

**Issue**: N+1 queries, inefficient loading
**Files Affected**:
- `src/dj/session_manager.py`

**Subtasks**:

4.2.1 **Fix N+1 query in find_tracks_for_theme**
- Use eager loading (joinedload)
- Implement pagination
- Reduce memory usage

```python
# Key changes:
from sqlalchemy.orm import joinedload

query = session.query(Track).options(
    joinedload(Track.analysis)
).filter(...)

# Paginate to avoid loading all tracks
for offset in range(0, min(total, limit), page_size):
    page = query.offset(offset).limit(page_size).all()
```

**Acceptance Criteria**:
- [ ] Query uses joinedload (no lazy loading)
- [ ] Results paginated in chunks
- [ ] Memory usage proportional to page_size, not total tracks
- [ ] Performance test: Query with 1000 tracks doesn't hang
- [ ] API test: Sessions still created successfully

**Estimated Time**: 3-4 hours
**Files to Modify**:
- Modify: `src/dj/session_manager.py` (~25 lines)

---

4.2.2 **Add database indexes for common queries**
- Index on (genre, artist)
- Index on (created_at) descending
- Test query performance

```python
# In database.py, add to Track class:
__table_args__ = (
    Index('idx_artist_genre', 'artist', 'genre'),
    Index('idx_created_at', 'created_at'),
)
```

**Acceptance Criteria**:
- [ ] Indexes created and verified
- [ ] Query plans use indexes (EXPLAIN)
- [ ] Query performance improved

**Estimated Time**: 2-3 hours
**Files to Modify**:
- Modify: `src/core/database.py` (~10 lines)

---

**Subtask Summary**:
- **Total Time**: ~5-7 hours
- **Testing**: Performance tests, API tests
- **Risk**: Low - optimization, shouldn't break functionality
- **Dependencies**: None

---

### TASK GROUP 5: Async Error Handling (2-3 days)

#### Task 5.1: Fix Async Task Management

**Issue**: Background tasks without proper exception handling
**Files Affected**:
- `src/main.py`

**Subtasks**:

5.1.1 **Implement background task tracking**
- Store task references
- Add exception handlers to all tasks
- Enable graceful cancellation

```python
# Key changes in RadioFreeLuna class:
class RadioFreeLuna:
    def __init__(self):
        self.background_tasks = []

    async def startup(self):
        # Create tasks and add to list
        task = asyncio.create_task(self.context_manager.start_monitoring())
        self.background_tasks.append(task)

        # Add exception handler
        def handle_exception(t):
            try:
                t.result()
            except asyncio.CancelledError:
                logger.info("Task cancelled")
            except Exception as e:
                logger.error(f"Task failed: {e}")

        task.add_done_callback(handle_exception)
```

**Acceptance Criteria**:
- [ ] All background tasks stored in list
- [ ] All tasks have exception handlers
- [ ] Exception handlers log properly
- [ ] No silent task failures
- [ ] Test: Verify exceptions are logged

**Estimated Time**: 3-4 hours
**Files to Modify**:
- Modify: `src/main.py` (~30 lines)

---

5.1.2 **Implement graceful shutdown for background tasks**
- Cancel all tasks on shutdown
- Wait for cancellation with timeout
- Handle tasks that don't respond

```python
# In RadioFreeLuna.shutdown():
async def shutdown(self):
    logger.info("Shutting down background tasks...")

    # Cancel all tasks
    for task in self.background_tasks:
        if not task.done():
            task.cancel()

    # Wait for cancellation
    try:
        await asyncio.wait_for(
            asyncio.gather(*self.background_tasks, return_exceptions=True),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        logger.warning("Some tasks didn't complete in time")
```

**Acceptance Criteria**:
- [ ] All tasks cancelled gracefully
- [ ] Wait with 5-second timeout
- [ ] Timeout handled gracefully
- [ ] Test: Verify clean shutdown

**Estimated Time**: 2-3 hours
**Files to Modify**:
- Modify: `src/main.py` (~20 lines)

---

**Subtask Summary**:
- **Total Time**: ~5-7 hours
- **Testing**: Shutdown test, exception test
- **Risk**: Medium - touches critical async patterns
- **Dependencies**: Task 2.1 (global state) should be done first

---

#### Task 5.2: Improve Error Handling in Shutdown

**Issue**: Incomplete cleanup on signal, data loss potential
**Files Affected**:
- `launch_radio_free_luna.py`

**Subtasks**:

5.2.1 **Implement async shutdown handler**
- Ensure databases flush
- Close all connections
- Log completion

```python
# New async handler:
async def handle_shutdown_async(app_instance):
    """Perform graceful shutdown"""
    logger.info("Starting graceful shutdown...")
    try:
        await app_instance.shutdown()
        logger.info("All systems shut down cleanly")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
```

**Acceptance Criteria**:
- [ ] Shutdown handler is async
- [ ] All systems properly shutdown
- [ ] No orphaned connections
- [ ] No data loss

**Estimated Time**: 2-3 hours
**Files to Modify**:
- Modify: `launch_radio_free_luna.py` (~20 lines)

---

5.2.2 **Fix signal handler to not exit immediately**
- Schedule shutdown task
- Wait for completion
- Exit cleanly

```python
# Updated signal handler:
def handle_shutdown(signum, frame):
    logger.info(f"Received signal {signum}")
    # Let uvicorn handle shutdown
    # Don't call sys.exit(0) immediately
```

**Acceptance Criteria**:
- [ ] Signal doesn't cause immediate exit
- [ ] Graceful shutdown completes
- [ ] Test: Kill with SIGTERM, verify clean shutdown

**Estimated Time**: 2-3 hours
**Files to Modify**:
- Modify: `launch_radio_free_luna.py` (~10 lines)

---

**Subtask Summary**:
- **Total Time**: ~4-6 hours
- **Testing**: Signal handling test, shutdown test
- **Risk**: Medium - critical path
- **Dependencies**: Task 5.1 should be done first

---

## Testing Strategy

For each task group, implement tests that verify the fix:

### Test Structure

```
tests/
├── test_security.py           # Config validation, credential removal
├── test_thread_safety.py      # Global state, race conditions
├── test_resources.py          # TTS cleanup, resource leaks
├── test_db_pooling.py         # Connection pooling, queries
├── test_input_validation.py   # Pydantic models, rate limiting
├── test_async_handling.py     # Task management, shutdown
```

### Test Coverage Targets

- **Unit Tests**: 80%+ of new code
- **Integration Tests**: All critical paths
- **Load Tests**: Verify fixes under stress

---

## Dependency Graph

```
Task 1 (Security) ──→ [Independent]
Task 2.1 (Global State) ──→ Task 2.2 (Resources) → Task 5.1 (Async)
Task 2.2 (Resources) ──→ Task 3.1 (DB Pooling) → Task 3.2 (Serialization)
Task 2.1 + 3.1 ──→ Task 5.2 (Shutdown)
Task 4.1 (Validation) ──→ [Independent, but test with 5.1]
Task 4.2 (Queries) ──→ [Requires 3.1 (Pooling)]
```

**Recommended Execution Order**:
1. Task 1 (Security) - No dependencies, high priority
2. Task 2.1 (Global State) - Foundation for Task 5
3. Task 2.2 (Resources) - Foundation for Task 5
4. Task 3.1 (DB Pooling) - Needed for queries/stress testing
5. Task 3.2 (Serialization) - Needed for session creation
6. Task 4.1 (Input Validation) - Can be parallel with others
7. Task 4.2 (Queries) - Needs pooling first
8. Task 5.1 (Async Tasks) - Needs global state first
9. Task 5.2 (Shutdown) - Last, integrates everything

---

## Daily Schedule (Example: 2-Week Sprint)

### Week 1
- **Day 1-2**: Task 1 (Security) + Task 2.1 (Global State)
- **Day 3-4**: Task 2.2 (Resources) + Task 3.1 (DB Pooling)
- **Day 5**: Task 3.2 (Serialization) + Task 4.1 (Validation)

### Week 2
- **Day 1-2**: Task 4.2 (Queries) + Integration testing
- **Day 3-4**: Task 5.1 (Async) + Task 5.2 (Shutdown)
- **Day 5**: Full system testing, documentation

---

## Success Criteria

Phase 1 is complete when:

1. **Security**
   - [ ] No hardcoded credentials
   - [ ] All config requires environment variables
   - [ ] Startup fails without required config

2. **Resource Management**
   - [ ] No resource leaks (connections, sessions)
   - [ ] Connection pool configured and working
   - [ ] All services cleanup properly

3. **Input Validation**
   - [ ] All endpoints validate input
   - [ ] Rate limiting prevents abuse
   - [ ] Invalid requests rejected with 422

4. **Error Handling**
   - [ ] Background tasks exceptions logged
   - [ ] Graceful shutdown completes
   - [ ] No data loss on shutdown

5. **Testing**
   - [ ] All critical paths tested
   - [ ] Load test passes (20+ concurrent requests)
   - [ ] Test suite passes without warnings

6. **Production Readiness**
   - [ ] System can be deployed to production
   - [ ] System handles 100+ concurrent requests
   - [ ] System recovers from service failures gracefully
   - [ ] All logs review clean (no error spam)

---

## Risk Mitigation

### Potential Risks

1. **Breaking Changes**
   - Mitigation: Add comprehensive integration tests
   - Mitigation: Use backward-compatible APIs where possible

2. **Missing Edge Cases**
   - Mitigation: Peer review each fix
   - Mitigation: Add stress testing

3. **Performance Regression**
   - Mitigation: Benchmark before/after each change
   - Mitigation: Load test to verify performance

4. **Incomplete Rollout**
   - Mitigation: Test each task independently
   - Mitigation: Merge to main only when complete

### Quality Gates

Before merging each task group:
- [ ] All tests pass
- [ ] Code review completed
- [ ] No performance regression
- [ ] Logs show no errors

---

## Effort Estimation Summary

| Task Group | Subtasks | Estimated Time |
|------------|----------|-----------------|
| 1. Security | 3 | 6-7 hours |
| 2. Global State | 2 | 6-8 hours |
| 2b. Resource Leaks | 2 | 4-6 hours |
| 3. DB Management | 2 | 15-17 hours |
| 3b. Serialization | 2 | 5-7 hours |
| 4. Input Validation | 2 | 14-16 hours |
| 4b. Query Fixes | 2 | 5-7 hours |
| 5. Async Handling | 2 | 9-13 hours |
| **TOTAL** | **17** | **~65-80 hours** |

**Estimated Duration**:
- At 8 hours/day: ~8-10 days
- At 4 hours/day: ~16-20 days
- **Realistic (with testing, review): 2-3 weeks**

---

## Next Steps

1. ✅ **Code Review Complete** (this document)
2. ✅ **Plan Created** (this file)
3. ⏭️ **BEGIN TASK 1**: Security & Configuration (when ready)
4. Follow execution order above
5. Daily status updates
6. Complete Phase 1 within 2-3 weeks

---

## Questions to Confirm

Before starting, confirm:

1. **Resources**: Is Todd available full-time for 2-3 weeks?
2. **Dependencies**: Is slowapi okay to add for rate limiting?
3. **Database**: Should we support both SQLite and PostgreSQL for pooling?
4. **Testing**: Create new test files or add to existing test_api.py?
5. **Deployment**: Any specific target environment (Windows, Linux, Docker)?

---

## End of Plan

This plan provides a clear path to production readiness. Each task is scoped, testable, and independent where possible. Following this plan should result in a production-ready system in 2-3 weeks.

Ready to begin?
