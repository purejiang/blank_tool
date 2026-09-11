#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hello — minimal builtin plugin (logic-only example).

Demonstrates the plugin contract: a module with a ``run(context, **params)``
function, optional metadata (DESCRIPTION/VERSION/AUTHOR) and an optional
``PARAMS`` declaration the frontend renders as a small form.

Contract: call ``context.complete(...)`` exactly once before returning.
"""

DESCRIPTION = "Hello world: echoes a greeting. Minimal logic-plugin example."
VERSION = "1.0.0"
AUTHOR = "blank_tool"

PARAMS = [
    {"key": "name", "label": "名字", "type": "string", "required": False, "default": "world"},
    {"key": "shout", "label": "大写喊出来", "type": "bool", "default": False},
]


def run(context, name: str = "world", shout: bool = False, **kwargs):
    context.log(f"hello: name={name!r} shout={shout}")
    message = f"Hello, {name}!"
    if shout:
        message = message.upper()
    result = {"message": message}
    context.complete(result)
    return result
