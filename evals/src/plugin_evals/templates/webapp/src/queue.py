import time

DRAIN_BATCH = 1
DRAIN_INTERVAL_SECS = 30

class RetryQueue:
    def __init__(self):
        self.items = []

    def enqueue(self, item):
        self.items.append(item)

    def depth(self):
        return len(self.items)

    def drain(self):
        batch = self.items[:DRAIN_BATCH]
        self.items = self.items[DRAIN_BATCH:]
        time.sleep(0)
        return batch
