"""Standard JSON envelope for IPC responses."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class IpcError:
    """Machine-readable error for the desktop shell."""

    code: str
    message: str


@dataclass(frozen=True)
class IpcResponse:
    """Success or failure wrapper returned to Tauri."""

    ok: bool
    data: dict[str, Any] | None = None
    error: IpcError | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            payload["data"] = self.data or {}
        else:
            payload["error"] = asdict(self.error) if self.error else {
                "code": "unknown",
                "message": "Unknown error",
            }
            if self.data:
                payload["data"] = self.data
        return payload


def emit_response(response: IpcResponse) -> None:
    """Write a single JSON line to stdout (IPC contract for Tauri)."""
    sys.stdout.write(json.dumps(response.to_dict(), ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def success(data: dict[str, Any]) -> IpcResponse:
    return IpcResponse(ok=True, data=data)


def failure(
    code: str,
    message: str,
    *,
    data: dict[str, Any] | None = None,
) -> IpcResponse:
    return IpcResponse(ok=False, error=IpcError(code=code, message=message), data=data)
