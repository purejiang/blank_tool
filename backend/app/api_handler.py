from typing import Callable
import threading
import importlib
import pkgutil
from app.utils.logger import Logger

class ApiHandler:
    def __init__(self, send_event: Callable[[str, dict], None]):
        self.send_event = send_event
        self.streaming_threads = {}
        self.logger = Logger.get_logger(self.__class__.__name__)
        self.api_map = self.load_handlers()

    def load_handlers(self) -> dict:
        api_map = {}
        handlers_package = 'app.handlers'
        package = importlib.import_module(handlers_package)
        for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
            module = importlib.import_module(name)
            if hasattr(module, 'API_MAP'):
                api_map.update(module.API_MAP)
        return api_map

    def handle_request(self, request_data):
        req_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params", {})

        response = {"id": req_id}
        handler = self.api_map.get(method)

        if not handler:
            response['error'] = {"code": -32601, "message": f"Method '{method}' not found"}
            return response

        try:
            streaming_methods = {"adb.logcat"}
            if method in streaming_methods:
                result = self.stream_handler(handler)(params)
            else:
                result = handler(params, None)
            response['result'] = result
            return response
        except Exception as e:
            self.logger.error(f"Error handling request (method={method}): {e}")
            response['error'] = {"code": -32000, "message": str(e)}
            return response

    def stream_handler(self, handler: Callable[[dict, Callable], None]):
        def wrapper(params):
            stream_id = f"{handler.__name__}-{len(self.streaming_threads) + 1}"
            stop_event = threading.Event()

            def stream_callback(data):
                self.send_event("stream.event", {"stream_id": stream_id, "data": data})

            def stream_wrapper(stop_event:threading.Event, stream_callback: Callable[[dict], None], params_dict:dict):
                try:
                    handler(params_dict, stream_callback)
                except Exception as e:
                    self.logger.error(f"流处理线程中发生错误: {e}")
                    stream_callback({"type": "error", "payload": {"message": str(e)}})

            thread = threading.Thread(target=stream_wrapper, args=(stop_event, stream_callback, params))
            thread.start()

            self.streaming_threads[stream_id] = (thread, stop_event)
            return {"stream_id": stream_id}
        return wrapper
