from src.queue import RetryQueue

queue = RetryQueue()

def upload(request):
    payload = request.body
    token = request.headers.get("X-Auth")
    if not token:
        return {"status": 401}
    queue.enqueue(payload)
    return {"status": 202, "queued": queue.depth()}
