"""框架无关、不可变的 Camera 聚合及完整配置变更行为。"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address
from uuid import UUID

from app.modules.cameras.domain.errors import (
    CameraAggregateCorruptedError,
    CameraDomainErrorCode,
    CameraFieldError,
    CameraValidationError,
    validation_error,
)
from app.modules.cameras.domain.ports import Clock, IdGenerator
from app.modules.cameras.domain.values import (
    CameraCredentials,
    build_rtsp_url,
    corrupted_issue,
    create_credentials,
    normalize_name,
    normalize_source_name,
    normalize_url_suffix,
    normalize_utc_datetime,
    rethrow_as_corruption,
    validate_ipv4,
    validate_rtsp_port,
    validate_uuid4,
)

type CameraId = UUID
type SourceId = UUID


@dataclass(frozen=True, slots=True)
class NewCameraSource:
    """创建 Camera 时的一路 Source 意图；正式 ID 只能由服务端生成。"""

    name: str
    url_suffix: str
    is_default_preview: bool = False


@dataclass(frozen=True, slots=True)
class CameraSourceChange:
    """完整更新中的 Source 意图；无 ID 表示新增，有 ID 表示保留。"""

    name: str
    url_suffix: str
    is_default_preview: bool = False
    source_id: SourceId | None = None


@dataclass(frozen=True, slots=True, init=False)
class CameraSource:
    """Camera 聚合内不可独立持久化的 Source 实体。"""

    source_id: SourceId
    camera_id: CameraId
    name: str
    url_suffix: str
    sort_order: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def _from_validated(
        cls,
        *,
        source_id: SourceId,
        camera_id: CameraId,
        name: str,
        url_suffix: str,
        sort_order: int,
        created_at: datetime,
        updated_at: datetime,
    ) -> "CameraSource":
        source = object.__new__(cls)
        object.__setattr__(source, "source_id", source_id)
        object.__setattr__(source, "camera_id", camera_id)
        object.__setattr__(source, "name", name)
        object.__setattr__(source, "url_suffix", url_suffix)
        object.__setattr__(source, "sort_order", sort_order)
        object.__setattr__(source, "created_at", created_at)
        object.__setattr__(source, "updated_at", updated_at)
        return source

    @classmethod
    def reconstitute(
        cls,
        *,
        source_id: SourceId,
        camera_id: CameraId,
        name: str,
        url_suffix: str,
        sort_order: int,
        created_at: datetime,
        updated_at: datetime,
    ) -> "CameraSource":
        """从持久化数据重建 Source；不对非规范值执行静默修复。"""

        issues: list[CameraFieldError] = []
        try:
            valid_source_id = validate_uuid4(source_id, field_name="source_id")
            valid_camera_id = validate_uuid4(camera_id, field_name="camera_id")
            normalized_name = normalize_source_name(name, field_name="name")
            normalized_suffix = normalize_url_suffix(url_suffix, field_name="url_suffix")
        except CameraValidationError as error:
            raise CameraAggregateCorruptedError(*rethrow_as_corruption(error)) from None

        if normalized_name != name:
            issues.append(corrupted_issue("name", "持久化的 Source 名称不是规范形式。"))
        if normalized_suffix != url_suffix:
            issues.append(corrupted_issue("url_suffix", "持久化的 URL 后缀不是规范形式。"))
        if isinstance(sort_order, bool) or not isinstance(sort_order, int) or sort_order < 0:
            issues.append(corrupted_issue("sort_order", "持久化的 Source 顺序无效。"))

        try:
            valid_created_at = normalize_utc_datetime(created_at)
            valid_updated_at = normalize_utc_datetime(updated_at)
        except ValueError:
            issues.append(corrupted_issue("created_at", "持久化的 Source 时间缺少时区。"))
            valid_created_at = valid_updated_at = created_at
        else:
            if valid_updated_at < valid_created_at:
                issues.append(corrupted_issue("updated_at", "Source 更新时间早于创建时间。"))

        if issues:
            raise CameraAggregateCorruptedError(*issues)
        return cls._from_validated(
            source_id=valid_source_id,
            camera_id=valid_camera_id,
            name=normalized_name,
            url_suffix=normalized_suffix,
            sort_order=sort_order,
            created_at=valid_created_at,
            updated_at=valid_updated_at,
        )


@dataclass(frozen=True, slots=True, init=False)
class Camera:
    """Camera 聚合根；所有变更返回新的合法聚合。"""

    camera_id: CameraId
    name: str
    ip_address: IPv4Address
    rtsp_port: int
    credentials: CameraCredentials
    default_preview_source_id: SourceId
    sources: tuple[CameraSource, ...]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def _from_validated(
        cls,
        *,
        camera_id: CameraId,
        name: str,
        ip_address: IPv4Address,
        rtsp_port: int,
        credentials: CameraCredentials,
        default_preview_source_id: SourceId,
        sources: tuple[CameraSource, ...],
        created_at: datetime,
        updated_at: datetime,
    ) -> "Camera":
        camera = object.__new__(cls)
        object.__setattr__(camera, "camera_id", camera_id)
        object.__setattr__(camera, "name", name)
        object.__setattr__(camera, "ip_address", ip_address)
        object.__setattr__(camera, "rtsp_port", rtsp_port)
        object.__setattr__(camera, "credentials", credentials)
        object.__setattr__(camera, "default_preview_source_id", default_preview_source_id)
        object.__setattr__(camera, "sources", sources)
        object.__setattr__(camera, "created_at", created_at)
        object.__setattr__(camera, "updated_at", updated_at)
        return camera

    @classmethod
    def create(
        cls,
        *,
        name: str,
        ip_address: str | IPv4Address,
        rtsp_port: int,
        username: str,
        password: str,
        sources: Sequence[NewCameraSource],
        id_generator: IdGenerator,
        clock: Clock,
    ) -> "Camera":
        """生成 ID 与时间，并一次创建完整且合法的 Camera 聚合。"""

        valid_name = normalize_name(name)
        valid_ip = validate_ipv4(ip_address)
        valid_port = validate_rtsp_port(rtsp_port)
        credentials = create_credentials(username, password)
        normalized_sources = _normalize_source_inputs(sources)
        now = _read_clock(clock)
        camera_id = _generate_id(id_generator, "camera_id")

        generated_source_ids: list[SourceId] = []
        source_entities: list[CameraSource] = []
        for index, source in enumerate(normalized_sources):
            source_id = _generate_id(id_generator, f"sources[{index}].source_id")
            if source_id in generated_source_ids or source_id == camera_id:
                raise _generated_duplicate_id(f"sources[{index}].source_id")
            generated_source_ids.append(source_id)
            source_entities.append(
                CameraSource._from_validated(
                    source_id=source_id,
                    camera_id=camera_id,
                    name=source.name,
                    url_suffix=source.url_suffix,
                    sort_order=index,
                    created_at=now,
                    updated_at=now,
                )
            )

        default_index = next(
            index for index, source in enumerate(normalized_sources) if source.is_default_preview
        )
        return cls._from_validated(
            camera_id=camera_id,
            name=valid_name,
            ip_address=valid_ip,
            rtsp_port=valid_port,
            credentials=credentials,
            default_preview_source_id=source_entities[default_index].source_id,
            sources=tuple(source_entities),
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def reconstitute(
        cls,
        *,
        camera_id: CameraId,
        name: str,
        ip_address: str | IPv4Address,
        rtsp_port: int,
        username: str,
        password: str,
        default_preview_source_id: SourceId,
        sources: Sequence[CameraSource],
        created_at: datetime,
        updated_at: datetime,
    ) -> "Camera":
        """从 Repository 重建聚合；检测到损坏时拒绝返回部分配置。"""

        try:
            valid_camera_id = validate_uuid4(camera_id, field_name="camera_id")
            valid_default_id = validate_uuid4(
                default_preview_source_id,
                field_name="default_preview_source_id",
            )
            valid_name = normalize_name(name)
            valid_ip = validate_ipv4(ip_address)
            valid_port = validate_rtsp_port(rtsp_port)
            credentials = create_credentials(username, password)
        except CameraValidationError as error:
            raise CameraAggregateCorruptedError(*rethrow_as_corruption(error)) from None

        issues: list[CameraFieldError] = []
        if valid_name != name:
            issues.append(corrupted_issue("name", "持久化的 Camera 名称不是规范形式。"))
        try:
            valid_created_at = normalize_utc_datetime(created_at)
            valid_updated_at = normalize_utc_datetime(updated_at)
        except ValueError:
            issues.append(corrupted_issue("created_at", "持久化的 Camera 时间缺少时区。"))
            valid_created_at = valid_updated_at = created_at
        else:
            if valid_updated_at < valid_created_at:
                issues.append(corrupted_issue("updated_at", "Camera 更新时间早于创建时间。"))

        source_tuple = tuple(sources)
        issues.extend(_aggregate_integrity_issues(valid_camera_id, valid_default_id, source_tuple))
        if issues:
            raise CameraAggregateCorruptedError(*issues)

        return cls._from_validated(
            camera_id=valid_camera_id,
            name=valid_name,
            ip_address=valid_ip,
            rtsp_port=valid_port,
            credentials=credentials,
            default_preview_source_id=valid_default_id,
            sources=source_tuple,
            created_at=valid_created_at,
            updated_at=valid_updated_at,
        )

    def update_configuration(
        self,
        *,
        name: str,
        ip_address: str | IPv4Address,
        rtsp_port: int,
        username: str,
        password: str,
        sources: Sequence[CameraSourceChange],
        id_generator: IdGenerator,
        clock: Clock,
    ) -> "Camera":
        """按 PUT 完整集合语义保留、新增、删除和重排 Source。"""

        valid_name = normalize_name(name)
        valid_ip = validate_ipv4(ip_address)
        valid_port = validate_rtsp_port(rtsp_port)
        credentials = create_credentials(username, password)
        normalized_sources = _normalize_source_inputs(sources)
        existing_by_id = {source.source_id: source for source in self.sources}
        _validate_changed_source_ids(normalized_sources, existing_by_id)
        now = _read_clock(clock, not_before=self.updated_at)

        used_ids = {
            source.source_id for source in normalized_sources if source.source_id is not None
        }
        new_sources: list[CameraSource] = []
        for index, source in enumerate(normalized_sources):
            if source.source_id is None:
                source_id = _generate_id(id_generator, f"sources[{index}].source_id")
                if (
                    source_id in used_ids
                    or source_id in existing_by_id
                    or source_id == self.camera_id
                ):
                    raise _generated_duplicate_id(f"sources[{index}].source_id")
                used_ids.add(source_id)
                created_at = updated_at = now
            else:
                source_id = source.source_id
                existing = existing_by_id[source_id]
                created_at = existing.created_at
                changed = (
                    existing.name != source.name
                    or existing.url_suffix != source.url_suffix
                    or existing.sort_order != index
                )
                updated_at = now if changed else existing.updated_at

            new_sources.append(
                CameraSource._from_validated(
                    source_id=source_id,
                    camera_id=self.camera_id,
                    name=source.name,
                    url_suffix=source.url_suffix,
                    sort_order=index,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )

        default_index = next(
            index for index, source in enumerate(normalized_sources) if source.is_default_preview
        )
        return self._from_validated(
            camera_id=self.camera_id,
            name=valid_name,
            ip_address=valid_ip,
            rtsp_port=valid_port,
            credentials=credentials,
            default_preview_source_id=new_sources[default_index].source_id,
            sources=tuple(new_sources),
            created_at=self.created_at,
            # PUT 是一次明确的聚合写入，即使值相同也记录本次服务端变更时间。
            updated_at=now,
        )

    def change_default_preview_source(self, source_id: SourceId, *, clock: Clock) -> "Camera":
        """切换到任意所属 Source，并仅推进聚合更新时间。"""

        valid_source_id = validate_uuid4(source_id, field_name="source_id")
        if valid_source_id not in {source.source_id for source in self.sources}:
            raise validation_error(
                "source_id",
                CameraDomainErrorCode.SOURCE_NOT_OWNED_BY_CAMERA,
                "Source 不存在或不属于当前 Camera。",
            )
        now = _read_clock(clock, not_before=self.updated_at)
        return self._from_validated(
            camera_id=self.camera_id,
            name=self.name,
            ip_address=self.ip_address,
            rtsp_port=self.rtsp_port,
            credentials=self.credentials,
            default_preview_source_id=valid_source_id,
            sources=self.sources,
            created_at=self.created_at,
            updated_at=now,
        )

    def is_default_preview(self, source_id: SourceId) -> bool:
        """派生默认标记，避免在 Camera 与 Source 中保存两份事实。"""

        return source_id == self.default_preview_source_id

    def rtsp_url_for(self, source_id: SourceId) -> str:
        """只在显式调用时生成带凭据 URL，结果不进入聚合状态。"""

        valid_source_id = validate_uuid4(source_id, field_name="source_id")
        source = next(
            (item for item in self.sources if item.source_id == valid_source_id),
            None,
        )
        if source is None:
            raise validation_error(
                "source_id",
                CameraDomainErrorCode.SOURCE_NOT_OWNED_BY_CAMERA,
                "Source 不存在或不属于当前 Camera。",
            )
        return build_rtsp_url(
            credentials=self.credentials,
            camera_ip=self.ip_address,
            rtsp_port=self.rtsp_port,
            url_suffix=source.url_suffix,
        )


@dataclass(frozen=True, slots=True)
class _NormalizedSourceInput:
    """内部规范化结果；不会跨出领域模块。"""

    name: str
    url_suffix: str
    is_default_preview: bool
    source_id: SourceId | None


def _normalize_source_inputs(
    sources: Sequence[NewCameraSource] | Sequence[CameraSourceChange],
) -> tuple[_NormalizedSourceInput, ...]:
    if not sources:
        raise validation_error(
            "sources",
            CameraDomainErrorCode.SOURCE_REQUIRED,
            "Camera 必须至少包含一路 Source。",
        )

    errors: list[CameraFieldError] = []
    default_indexes = [
        index for index, source in enumerate(sources) if source.is_default_preview is True
    ]
    if not default_indexes:
        errors.append(
            CameraFieldError(
                field="sources",
                code=CameraDomainErrorCode.DEFAULT_SOURCE_REQUIRED,
                detail="请选择一路默认预览 Source。",
            )
        )
    elif len(default_indexes) > 1:
        errors.extend(
            CameraFieldError(
                field=f"sources[{index}].is_default_preview",
                code=CameraDomainErrorCode.MULTIPLE_DEFAULT_SOURCES,
                detail="只能选择一路默认预览 Source。",
            )
            for index in default_indexes[1:]
        )

    normalized: list[_NormalizedSourceInput] = []
    suffix_first_index: dict[str, int] = {}
    for index, source in enumerate(sources):
        try:
            source_name = normalize_source_name(
                source.name,
                field_name=f"sources[{index}].name",
            )
            suffix = normalize_url_suffix(
                source.url_suffix,
                field_name=f"sources[{index}].url_suffix",
            )
        except CameraValidationError as error:
            errors.extend(error.errors)
            continue

        if suffix in suffix_first_index:
            errors.append(
                CameraFieldError(
                    field=f"sources[{index}].url_suffix",
                    code=CameraDomainErrorCode.DUPLICATE_SOURCE_SUFFIX,
                    detail="同一 Camera 内的视频源 URL 后缀不能重复。",
                )
            )
        else:
            suffix_first_index[suffix] = index

        normalized.append(
            _NormalizedSourceInput(
                name=source_name,
                url_suffix=suffix,
                is_default_preview=source.is_default_preview is True,
                source_id=getattr(source, "source_id", None),
            )
        )

    if errors:
        raise CameraValidationError(*errors)
    return tuple(normalized)


def _validate_changed_source_ids(
    sources: Sequence[_NormalizedSourceInput],
    existing_by_id: dict[SourceId, CameraSource],
) -> None:
    errors: list[CameraFieldError] = []
    seen: set[SourceId] = set()
    for index, source in enumerate(sources):
        if source.source_id is None:
            continue
        try:
            valid_source_id = validate_uuid4(
                source.source_id,
                field_name=f"sources[{index}].source_id",
            )
        except CameraValidationError as error:
            errors.extend(error.errors)
            continue
        if valid_source_id in seen:
            errors.append(
                CameraFieldError(
                    field=f"sources[{index}].source_id",
                    code=CameraDomainErrorCode.DUPLICATE_SOURCE_ID,
                    detail="请求中的 Source ID 不能重复。",
                )
            )
        elif valid_source_id not in existing_by_id:
            errors.append(
                CameraFieldError(
                    field=f"sources[{index}].source_id",
                    code=CameraDomainErrorCode.SOURCE_NOT_OWNED_BY_CAMERA,
                    detail="Source 不存在或不属于当前 Camera。",
                )
            )
        seen.add(valid_source_id)

    if errors:
        raise CameraValidationError(*errors)


def _aggregate_integrity_issues(
    camera_id: CameraId,
    default_source_id: SourceId,
    sources: tuple[CameraSource, ...],
) -> list[CameraFieldError]:
    issues: list[CameraFieldError] = []
    if not sources:
        issues.append(corrupted_issue("sources", "持久化的 Camera 没有 Source。"))
        return issues

    seen_ids: set[SourceId] = set()
    seen_suffixes: set[str] = set()
    for index, source in enumerate(sources):
        if source.camera_id != camera_id:
            issues.append(
                corrupted_issue(f"sources[{index}].camera_id", "Source 不属于当前 Camera。")
            )
        if source.source_id == camera_id:
            issues.append(
                corrupted_issue(
                    f"sources[{index}].source_id",
                    "Camera 与 Source 使用了重复的全局业务 ID。",
                )
            )
        if source.source_id in seen_ids:
            issues.append(corrupted_issue(f"sources[{index}].source_id", "Source ID 重复。"))
        if source.url_suffix in seen_suffixes:
            issues.append(corrupted_issue(f"sources[{index}].url_suffix", "Source URL 后缀重复。"))
        if source.sort_order != index:
            issues.append(corrupted_issue(f"sources[{index}].sort_order", "Source 顺序不连续。"))
        seen_ids.add(source.source_id)
        seen_suffixes.add(source.url_suffix)

    if default_source_id not in seen_ids:
        issues.append(
            corrupted_issue(
                "default_preview_source_id",
                "默认 Source 不存在或不属于当前 Camera。",
            )
        )
    return issues


def _generate_id(generator: IdGenerator, field_name: str) -> UUID:
    """拒绝错误生成器产生的非 v4 ID，不自动重试或掩盖配置问题。"""

    try:
        return validate_uuid4(generator.new_id(), field_name=field_name)
    except CameraValidationError as error:
        raise CameraAggregateCorruptedError(*error.errors) from None


def _generated_duplicate_id(field_name: str) -> CameraAggregateCorruptedError:
    """把服务端 ID 生成器碰撞与客户端重复 ID 校验明确区分。"""

    return CameraAggregateCorruptedError(
        CameraFieldError(
            field=field_name,
            code=CameraDomainErrorCode.DUPLICATE_SOURCE_ID,
            detail="服务端 ID 生成器产生了重复业务 ID。",
        )
    )


def _read_clock(clock: Clock, *, not_before: datetime | None = None) -> datetime:
    """读取 UTC 时钟并防止更新时间倒退。"""

    try:
        now = normalize_utc_datetime(clock.now())
    except ValueError:
        raise CameraAggregateCorruptedError(
            corrupted_issue("updated_at", "注入时钟返回了无时区时间。")
        ) from None
    if not_before is not None and now < not_before:
        raise CameraAggregateCorruptedError(
            corrupted_issue("updated_at", "注入时钟早于聚合当前更新时间。")
        )
    return now
