from src.appconfig import format_count

def summarize(items):
    return f"{format_count(len(items))} items"
