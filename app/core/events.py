"""Bus de eventos interno (síncrono, en proceso) — task pack §19.

Objetivo: desacoplar Operación de Negocio → Evento Financiero → Contabilidad.
Un suscriptor que falla se registra en el log pero nunca tumba al publicador.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("arca.events")

Handler = Callable[[str, dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Handler) -> None:
        self._handlers[event_name].append(handler)

    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        logger.debug("evento %s %s", event_name, payload)
        for handler in self._handlers.get(event_name, []):
            try:
                handler(event_name, payload)
            except Exception:  # noqa: BLE001 - un suscriptor no debe tumbar la operación
                logger.exception("suscriptor falló para evento %s", event_name)


event_bus = EventBus()
