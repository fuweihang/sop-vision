"""Small schema-driven PySide form used by the external-client demo."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SchemaValidationError(ValueError):
    pass


class SchemaForm(QWidget):
    """Render standard JSON Schema properties and return a validated object."""

    def __init__(self) -> None:
        super().__init__()
        self._schema: dict[str, Any] = {"type": "object", "properties": {}}
        self._editor: _ObjectEditor | None = None
        self._layout = QVBoxLayout(self)
        self._placeholder = QLabel("请先从守护进程加载 Worker Schema")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._placeholder)

    def set_schema(
        self,
        schema: dict[str, Any],
        value: dict[str, Any] | None = None,
    ) -> None:
        self.clear()
        self._schema = schema
        self._editor = _ObjectEditor(schema, schema)
        self._layout.addWidget(self._editor)
        self._editor.set_value(value or {})

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._editor = None

    def payload(self) -> dict[str, Any]:
        if self._editor is None:
            raise SchemaValidationError("尚未加载配置 Schema")
        value = self._editor.value()
        errors = sorted(
            Draft202012Validator(self._schema).iter_errors(value),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = ".".join(str(part) for part in error.absolute_path) or "config"
            raise SchemaValidationError(f"{location}: {error.message}")
        return value


class _ObjectEditor(QWidget):
    def __init__(self, schema: dict[str, Any], root_schema: dict[str, Any]) -> None:
        super().__init__()
        self._schema = schema
        self._root_schema = root_schema
        self._required = set(schema.get("required", []))
        self._editors: dict[str, _ValueEditor] = {}
        layout = QFormLayout(self)
        for name, raw_property in schema.get("properties", {}).items():
            property_schema = _resolve_schema(raw_property, root_schema)
            editor = _ValueEditor(
                property_schema,
                root_schema,
                optional=name not in self._required,
            )
            self._editors[name] = editor
            title = property_schema.get("title", name)
            label = QLabel(f"{title}{' *' if name in self._required else ''}")
            description = property_schema.get("description")
            if description:
                label.setToolTip(str(description))
                editor.setToolTip(str(description))
            layout.addRow(label, editor)

    def value(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, editor in self._editors.items():
            included, value = editor.read_value()
            if included:
                result[name] = value
        return result

    def set_value(self, value: dict[str, Any]) -> None:
        for name, editor in self._editors.items():
            if name in value:
                editor.set_value(value[name], included=True)
            else:
                editor.set_default()


class _ValueEditor(QWidget):
    def __init__(
        self,
        schema: dict[str, Any],
        root_schema: dict[str, Any],
        *,
        optional: bool,
    ) -> None:
        super().__init__()
        self._schema = schema
        self._optional = optional
        schema, nullable = _unwrap_nullable(schema, root_schema)
        self._value_schema = schema
        self._nullable = nullable
        self._enabled = QCheckBox("启用") if optional else None
        self._null = QCheckBox("null") if nullable else None
        self._widget = _build_widget(schema, root_schema)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if self._enabled is not None:
            layout.addWidget(self._enabled)
            self._enabled.toggled.connect(self._sync_enabled)
        if self._null is not None:
            layout.addWidget(self._null)
            self._null.toggled.connect(self._sync_enabled)
        layout.addWidget(self._widget, stretch=1)
        self._sync_enabled()

    def set_default(self) -> None:
        if "default" in self._schema:
            self.set_value(self._schema["default"], included=True)
        elif self._optional:
            self.set_value(None, included=False)
        else:
            _set_widget_default(self._widget, self._value_schema)

    def set_value(self, value: Any, *, included: bool = True) -> None:
        if self._enabled is not None:
            self._enabled.setChecked(included)
        if self._null is not None:
            self._null.setChecked(included and value is None)
        if value is not None:
            _set_widget_value(self._widget, value)
        self._sync_enabled()

    def read_value(self) -> tuple[bool, Any]:
        if self._enabled is not None and not self._enabled.isChecked():
            return False, None
        if self._null is not None and self._null.isChecked():
            return True, None
        return True, _read_widget_value(self._widget, self._value_schema)

    def _sync_enabled(self, _checked: bool | None = None) -> None:
        included = self._enabled is None or self._enabled.isChecked()
        is_null = self._null is not None and self._null.isChecked()
        if self._null is not None:
            self._null.setEnabled(included)
        self._widget.setEnabled(included and not is_null)


def _build_widget(schema: dict[str, Any], root_schema: dict[str, Any]) -> QWidget:
    enum = schema.get("enum")
    if isinstance(enum, list):
        widget = QComboBox()
        for item in enum:
            widget.addItem(str(item), item)
        return widget
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        return _ObjectEditor(schema, root_schema)
    if schema_type == "array":
        widget = QPlainTextEdit()
        widget.setMaximumHeight(90)
        widget.setPlaceholderText("JSON array")
        return widget
    if schema_type == "boolean":
        return QCheckBox()
    if schema_type == "integer":
        widget = QSpinBox()
        minimum = int(schema.get("minimum", -2_147_483_648))
        maximum = int(schema.get("maximum", 2_147_483_647))
        if "exclusiveMinimum" in schema:
            minimum = int(schema["exclusiveMinimum"]) + 1
        if "exclusiveMaximum" in schema:
            maximum = int(schema["exclusiveMaximum"]) - 1
        widget.setRange(minimum, maximum)
        return widget
    if schema_type == "number":
        widget = QDoubleSpinBox()
        widget.setDecimals(6)
        widget.setRange(
            float(schema.get("minimum", -1e12)), float(schema.get("maximum", 1e12))
        )
        if "exclusiveMinimum" in schema:
            widget.setMinimum(float(schema["exclusiveMinimum"]) + 1e-6)
        if "exclusiveMaximum" in schema:
            widget.setMaximum(float(schema["exclusiveMaximum"]) - 1e-6)
        return widget
    return QLineEdit()


def _read_widget_value(widget: QWidget, schema: dict[str, Any]) -> Any:
    if isinstance(widget, _ObjectEditor):
        return widget.value()
    if isinstance(widget, QPlainTextEdit):
        try:
            value = json.loads(widget.toPlainText() or "[]")
        except json.JSONDecodeError as error:
            raise SchemaValidationError(f"数组 JSON 无效: {error.msg}") from error
        return value
    if isinstance(widget, QComboBox):
        return widget.currentData()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QLineEdit):
        return widget.text()
    raise TypeError(f"unsupported schema widget: {type(widget).__name__}")


def _set_widget_value(widget: QWidget, value: Any) -> None:
    if isinstance(widget, _ObjectEditor) and isinstance(value, dict):
        widget.set_value(value)
    elif isinstance(widget, QPlainTextEdit):
        widget.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))
    elif isinstance(widget, QComboBox):
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)
    elif isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QSpinBox):
        widget.setValue(int(value))
    elif isinstance(widget, QDoubleSpinBox):
        widget.setValue(float(value))
    elif isinstance(widget, QLineEdit):
        widget.setText(str(value))


def _set_widget_default(widget: QWidget, schema: dict[str, Any]) -> None:
    if "default" in schema:
        _set_widget_value(widget, schema["default"])
    elif isinstance(widget, QPlainTextEdit):
        widget.setPlainText("[]")
    elif isinstance(widget, _ObjectEditor):
        widget.set_value({})


def _unwrap_nullable(
    schema: dict[str, Any], root_schema: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    variants = schema.get("anyOf")
    if not isinstance(variants, list):
        return schema, schema.get("type") == "null"
    non_null = [item for item in variants if item.get("type") != "null"]
    nullable = len(non_null) != len(variants)
    if len(non_null) == 1:
        resolved = _resolve_schema(non_null[0], root_schema)
        merged = {key: value for key, value in schema.items() if key != "anyOf"}
        merged.update(resolved)
        return merged, nullable
    return schema, nullable


def _resolve_schema(
    schema: dict[str, Any], root_schema: dict[str, Any]
) -> dict[str, Any]:
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return schema
    current: Any = root_schema
    for part in reference[2:].split("/"):
        current = current[part.replace("~1", "/").replace("~0", "~")]
    merged = dict(current)
    merged.update({key: value for key, value in schema.items() if key != "$ref"})
    return merged
