## Problem
Uploads are unbounded; enforce MAX_PER_MINUTE.

Claims from triage:
- validate_limit stub lives in src/limiter.py
- the upload entrypoint lives in src/handler.py
