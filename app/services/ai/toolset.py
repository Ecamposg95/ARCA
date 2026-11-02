"""Adaptador del catálogo de `app/agents/tools.py` al formato de herramientas de Claude.

No cambia el catálogo ni sus schemas Pydantic: deriva de cada `params_model`
un JSON Schema apto para `strict: true` (additionalProperties: false, todas
las propiedades en `required`, las opcionales aceptan null, sin restricciones
numéricas ni de longitud que el API no soporta; Pydantic las valida después).
El orden es determinista para que la lista se sirva desde caché.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agents.tools import TOOLS, ToolSpec

_UNSUPPORTED_KEYS = {
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems", "default", "title",
}


def _nullable(schema: dict) -> dict:
    """Permite null sin duplicar si ya lo acepta."""
    if schema.get("type") == "null":
        return schema
    if "anyOf" in schema:
        if any(opt.get("type") == "null" for opt in schema["anyOf"]):
            return schema
        return {**schema, "anyOf": [*schema["anyOf"], {"type": "null"}]}
    description = schema.get("description")
    inner = {k: v for k, v in schema.items() if k != "description"}
    out: dict[str, Any] = {"anyOf": [inner, {"type": "null"}]}
    if description:
        out["description"] = description
    return out


def _clean(node: Any) -> Any:
    if isinstance(node, list):
        return [_clean(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {k: _clean(v) for k, v in node.items() if k not in _UNSUPPORTED_KEYS}
    if out.get("type") == "object" and "properties" in out:
        required = set(out.get("required") or [])
        for name, prop in out["properties"].items():
            if name not in required:
                out["properties"][name] = _nullable(prop)
        out["required"] = list(out["properties"].keys())
        out["additionalProperties"] = False
    return out


def strict_schema(model: type[BaseModel]) -> dict:
    schema = copy.deepcopy(model.model_json_schema())
    schema = _clean(schema)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    schema.setdefault("required", [])
    schema["additionalProperties"] = False
    return schema


def anthropic_tool(tool: ToolSpec) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,
        "strict": True,
        "input_schema": strict_schema(tool.params_model),
    }


def tool_specs(names: list[str] | None = None) -> list[dict]:
    """Lista en el orden del catálogo (determinista); el último lleva cache_control."""
    chosen = [TOOLS[n] for n in TOOLS if names is None or n in names]
    specs = [anthropic_tool(t) for t in chosen]
    if specs:
        specs[-1] = {**specs[-1], "cache_control": {"type": "ephemeral"}}
    return specs


def validate_input(tool: ToolSpec, raw: Any) -> BaseModel:
    """`tool_use.input` llega como dict; se valida contra el schema del catálogo.

    Los null que el modo estricto obliga a mandar en campos opcionales se quitan
    para que apliquen los defaults del schema Create vigente.
    """
    if not isinstance(raw, dict):
        raise ValueError("los argumentos deben ser un objeto")
    cleaned = {k: v for k, v in raw.items() if v is not None}
    try:
        return tool.params_model.model_validate(cleaned)
    except ValidationError as exc:
        raise ValueError("Argumentos inválidos: " + "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5]
        ))
