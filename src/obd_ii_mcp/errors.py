from __future__ import annotations


class ObdError(Exception):
    code = "obd_error"

    def as_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": str(self)}


class NoAdapterFoundError(ObdError):
    code = "no_adapter_found"


class NoEcuResponseError(ObdError):
    code = "no_ecu_response"


class UnsupportedPidError(ObdError):
    code = "unsupported_pid"


class MalformedResponseError(ObdError):
    code = "malformed_response"


class AdapterTimeoutError(ObdError):
    code = "timeout"
