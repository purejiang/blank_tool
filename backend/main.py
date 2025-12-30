import sys
import os
import json
from pathlib import Path
import threading
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor

# 将backend目录添加到sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.api_handler import ApiHandler
from app.utils.logger import Logger
from app.utils.env import get_env, load_dotenv, resolve_path

# Thread-safe lock for writing to stdout
stdout_lock = threading.Lock()

def send_json(data: Dict[str, Any]):
    """Safely sends a JSON object to stdout."""
    with stdout_lock:
        sys.stdout.write(json.dumps(data) + '\n')
        sys.stdout.flush()

# Legacy send_event function is no longer needed by ApiHandler but might be used elsewhere?
# ApiHandler now uses send_json directly.

def bootstrap():
    # Load .env file
    load_dotenv()
    
    # Use environment variable for cache directory
    cache_dir = get_env('BT_CACHE_DIR', './cache')
    resolved_cache_dir = resolve_path(cache_dir)
    logs_file_path = Path(resolved_cache_dir) / "logs"
    
    log_level = get_env('BT_LOG_LEVEL', 'DEBUG')
    Logger.initialize(log_dir=logs_file_path, log_level=log_level)

def main():
    """Main loop to read requests from stdin and process them."""
    try:
        bootstrap()
        # ApiHandler now takes send_json directly
        api_handler = ApiHandler(send_response=send_json)
    except Exception as e:
        error_msg = f"Initialization failed: {e}"
        sys.stderr.write(error_msg + "\n")
        sys.stderr.flush()
        send_json({
            "id": None,
            "error": {"code": -32603, "message": error_msg}
        })
        sys.exit(1)

    executor = ThreadPoolExecutor(max_workers=4)

    def process_request(line):
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            
            # handle_request now returns the response structure directly
            response = api_handler.handle_request(request)
            
            if response:
                send_json(response)
                
        except json.JSONDecodeError:
            send_json({
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            })
        except Exception as e:
            send_json({
                "id": request_id,
                "error": {"code": -32603, "message": f"Internal error: {e}"}
            })

    for line in sys.stdin:
        executor.submit(process_request, line)

if __name__ == "__main__":
    main()