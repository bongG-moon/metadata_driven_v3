from __future__ import annotations

import sys
import types


class _Component:
    pass


class _Field:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _DropdownField(_Field):
    pass


class _Data:
    def __init__(self, data=None, **kwargs):
        self.data = data
        self.text = kwargs.get("text", "")


class _Message:
    def __init__(self, text="", **kwargs):
        self.text = text
        self.data = kwargs.get("data", {})


def _ensure_module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


lfx = _ensure_module("lfx")
custom = _ensure_module("lfx.custom")
custom_component = _ensure_module("lfx.custom.custom_component")
component = _ensure_module("lfx.custom.custom_component.component")
io = _ensure_module("lfx.io")
schema = _ensure_module("lfx.schema")
schema_data = _ensure_module("lfx.schema.data")
schema_message = _ensure_module("lfx.schema.message")

component.Component = _Component
io.DataInput = _Field
io.DropdownInput = _DropdownField
io.MessageTextInput = _Field
io.Output = _Field
schema_data.Data = _Data
schema_message.Message = _Message

lfx.custom = custom
custom.custom_component = custom_component
custom_component.component = component
lfx.io = io
lfx.schema = schema
schema.data = schema_data
schema.message = schema_message
