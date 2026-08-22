## Problem
Uploads are unbounded; enforce MAX_PER_MINUTE.

## Tasks
- [ ] T1: Implement validate_limit in src/limiter.py so tests/test_limiter.py passes (True when count <= MAX_PER_MINUTE, ValueError above)
- [ ] T2: Enforce the limit in src/handler.py upload via validate_limit so tests/test_handler.py passes (429 when over)
