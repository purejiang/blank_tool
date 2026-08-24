from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BackendSuccessPayload:
    type: str = 'success'
    payload: Any = None

    def to_dict(self) -> dict:
        return {'type': self.type, 'payload': self.payload}


@dataclass
class BackendErrorPayload:
    message: str
    code: Optional[int] = None

    def to_dict(self) -> dict:
        result: dict = {'type': 'error', 'payload': {'message': self.message}}
        if self.code is not None:
            result['payload']['code'] = self.code
        return result


# Standard JSON-RPC error codes
class ErrorCode:
    PARSE_ERROR = -32700
    METHOD_NOT_FOUND = -32601
    INTERNAL_ERROR = -32603
