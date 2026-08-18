"""守护进程 HTTP 命令的公开响应模型。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CommandName(StrEnum):
    START = "start"
    RELOAD = "reload"
    RESTART = "restart"
    STOP = "stop"


class RuntimeState(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class CommandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    command: CommandName
    runtime_state: RuntimeState
    pid: int | None
    config_revision: str
    forced_stop: bool = False


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    config_readable: bool
