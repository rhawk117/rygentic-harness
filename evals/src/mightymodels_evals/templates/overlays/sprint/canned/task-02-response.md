CANNED ENGINEER RESPONSE — task T2

Apply this patch as the engineer's work (write the file exactly):
--- src/handler.py ---
from src.limiter import validate_limit

def upload(payload, count):
    try:
        validate_limit(count)
    except ValueError:
        return {"status": 429}
    return {"status": 202}
--- end ---

Append to the brief:
## DONE
what: handler consults validate_limit; over-limit returns 429
commit: (local) t2-enforce-limit
diff-summary: src/handler.py — wrapped upload in limit check, 429 on ValueError
commands-run: python -m pytest tests/test_handler.py -q -> 1 passed

XML report:
<report><status>done</status><group>T2</group><tasks><task id="T2" verified="true"/></tasks><files_changed><file>src/handler.py</file></files_changed><deviation>none</deviation></report>
