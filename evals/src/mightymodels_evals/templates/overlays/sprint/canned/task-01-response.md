CANNED ENGINEER RESPONSE — task T1

Apply this patch as the engineer's work (write the file exactly):
--- src/limiter.py ---
MAX_PER_MINUTE = 30

def validate_limit(count):
    if count <= MAX_PER_MINUTE:
        return True
    raise ValueError(f"limit exceeded: {count} > {MAX_PER_MINUTE}")
--- end ---

Append to the brief:
## DONE
what: implemented validate_limit per AC; True at or under MAX_PER_MINUTE, ValueError above
commit: (local) t1-validate-limit
diff-summary: src/limiter.py — replaced NotImplementedError with threshold check and error message
commands-run: python -m pytest tests/test_limiter.py -q -> 1 passed

XML report:
<report><status>done</status><group>T1</group><tasks><task id="T1" verified="true"/></tasks><files_changed><file>src/limiter.py</file></files_changed><deviation>none</deviation></report>
