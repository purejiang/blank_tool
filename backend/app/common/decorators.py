from functools import wraps

def streaming(func):
    """
    Decorator to mark a handler as a streaming handler.
    Streaming handlers run in a separate thread and can send multiple events.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    
    wrapper.is_streaming = True
    return wrapper
