from dataclasses import dataclass, field, asdict
from typing import Any, Generic, TypeVar, Optional, Union
import json

T = TypeVar('T')

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

@dataclass
class BackendResponse:
    id: Any
    result: Union[BackendSuccessPayload, BackendErrorPayload, dict]
    finished: bool = True
    stream_id: Optional[str] = None

    def to_json(self) -> str:
        data = {
            'id': self.id,
            'result': self.result.to_dict() if isinstance(self.result, (BackendSuccessPayload, BackendErrorPayload)) else self.result,
            'finished': self.finished,
        }
        if self.stream_id:
            data['stream_id'] = self.stream_id
        return json.dumps(data)

@dataclass
class BackendStreamEvent:
    id: Any
    result: Union[BackendSuccessPayload, BackendErrorPayload, dict]
    stream_id: str

    def to_json(self) -> str:
        return json.dumps({
            'id': self.id,
            'result': self.result.to_dict() if isinstance(self.result, (BackendSuccessPayload, BackendErrorPayload)) else self.result,
            'stream_id': self.stream_id,
            'finished': False,
        })

@dataclass
class BackendApiRequest:
    id: Any
    method: str
    params: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict) -> 'BackendApiRequest':
        return cls(
            id=data.get('id'),
            method=data.get('method', ''),
            params=data.get('params', {})
        )

# Standard JSON-RPC error codes
class ErrorCode:
    PARSE_ERROR = -32700
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    TIMEOUT = -32000
    TOOL_ERROR = -32001
