from typing import Callable, Any
import threading
import importlib
import pkgutil
import uuid
from app.utils.logger import Logger

class ApiHandler:
    def __init__(self, send_response: Callable[[dict], None]):
        self.send_response = send_response
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

        handler = self.api_map.get(method)

        if not handler:
            return {
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found"}
            }

        try:
            # Check if handler is marked as streaming (via decorator) or is in legacy hardcoded list
            is_streaming = getattr(handler, 'is_streaming', False)
            
            if is_streaming:
                # Pass request_id to stream_handler
                result = self.stream_handler(handler, req_id)(params)
                # Return initial response indicating stream started
                return {"id": req_id, "result": result, "finished": False}
            else:
                raw_result = handler(params, None)
                # Automatic wrapping
                if isinstance(raw_result, dict) and "type" in raw_result:
                    result = raw_result
                else:
                    result = {"type": "success", "payload": raw_result}
                
                return {"id": req_id, "result": result, "finished": True}
        except Exception as e:
            self.logger.error(f"Error handling request (method={method}): {e}")
            return {
                "id": req_id, 
                "result": {"type": "error", "payload": {"message": str(e)}},
                "finished": True
            }

    def stream_handler(self, handler: Callable[[dict, Callable], None], request_id: Any):
        def wrapper(params):
            stream_id = f"{handler.__name__}-{str(uuid.uuid4())}"
            stop_event = threading.Event()

            def stream_callback(data):
                # Send stream data associated with request_id
                response = {
                    "id": request_id,
                    "result": data,
                    "stream_id": stream_id,
                    "finished": False
                }
                self.send_response(response)

            def stream_wrapper(stop_event:threading.Event, stream_callback: Callable[[dict], None], params_dict:dict):
                try:
                    handler(params_dict, stream_callback)
                except Exception as e:
                    self.logger.error(f"Error in stream thread: {e}")
                    stream_callback({"type": "error", "payload": {"message": str(e)}})
                finally:
                    # Send finished signal when thread exits
                    self.send_response({
                        "id": request_id,
                        "stream_id": stream_id,
                        "finished": True
                    })

            thread = threading.Thread(target=stream_wrapper, args=(stop_event, stream_callback, params))
            thread.start()

            self.streaming_threads[stream_id] = (thread, stop_event)
            return {"stream_id": stream_id}
        return wrapper
