import sys
import os
import json
from pathlib import Path
import threading
from typing import Dict, Any


# 将backend目录添加到sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.api_handler import ApiHandler
from app.utils.logger import Logger
from app.utils.env import get_env

# Thread-safe lock for writing to stdout
stdout_lock = threading.Lock()

def send_json(data: Dict[str, Any]):
    """Safely sends a JSON object to stdout."""
    with stdout_lock:
        sys.stdout.write(json.dumps(data) + '\n')
        sys.stdout.flush()

def send_event(event_name: str, data: Any):
    """Sends an event to the frontend."""
    send_json({"type": "event", "event": event_name, "data": data})

def bootstrap():
    logs_file_path = Path(__file__).parent / "cache" / "logs"
    log_level = get_env('BT_LOG_LEVEL', 'DEBUG')
    Logger.initialize(log_dir=logs_file_path, log_level=log_level)

    resources_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    java_bin = os.path.join(resources_dir, 'runtime', 'jre', 'bin', 'java.exe' if os.name == 'nt' else 'java')
    if os.path.exists(java_bin):
        os.environ['BT_JAVA_BIN'] = java_bin
        bin_dir = os.path.dirname(java_bin)
        os.environ['PATH'] = bin_dir + os.pathsep + os.environ.get('PATH', '')

def main():
    """Main loop to read requests from stdin and process them."""
    api_handler = None
    try:
        bootstrap()
        api_handler = ApiHandler(send_event=send_event)
    except Exception as e:
        send_json({
            "id": None,
            "error": {"code": -32603, "message": f"Initialization failed: {e}"}
        })
        return

    for line in sys.stdin:
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            response = api_handler.handle_request(request)
            # Notifications do not have a response, so we only send if one exists.
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

if __name__ == "__main__":
    main()