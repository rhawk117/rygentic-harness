## Problem
The retry queue drains one item every 30s regardless of depth (src/queue.py). Replace with adaptive batching, keep auth behavior in src/handler.py unchanged, add depth metrics.
