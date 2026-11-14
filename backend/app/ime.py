"""Psaní na TV přes IME (Android TV Remote protocol v2).

Postup podle funkční implementace sofa-remote (MIT, github.com/andreconde21/sofa-remote)
a podle logů z Philips 55PUS8818:

- Otevřené textové pole hlásí TV zprávou remote_ime_key_inject:
  app_info.counter = čítač IME relace, text_field_status.counter_field = čítač pole.
  Obě hodnoty musí každá úprava vracet. (androidtvremote2 bere čítače z ozvěny
  remote_ime_batch_edit, kde je vždy 1 – proto TV text zahazovala; viz HA issue #188164.)
- TV text vždy VKLÁDÁ na pozici kurzoru, nikdy nenahrazuje. Mazání = klávesa DEL.
- Po každé úpravě TV pošle remote_ime_show_request se skutečným obsahem pole a novým
  čítačem pole. Další úprava se posílá až po této ozvěně.
- remote_ime_batch_edit s ime_counter 0 od TV = klávesnice se zavřela.
- Písmena jako klávesy (KEYCODE_A …) TV přes tento protokol nepřijímá.
- Aplikace s vlastní klávesnicí (Netflix) pole nehlásí a text přijmou jen s čítači 0.
  Po zavření systémového pole nebo změně aplikace se proto čítače nulují.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from androidtvremote2 import AndroidTVRemote, ConnectionClosed
from androidtvremote2.remote import RemoteProtocol
from androidtvremote2.remotemessage_pb2 import (
    RemoteEditInfo,
    RemoteImeBatchEdit,
    RemoteImeObject,
    RemoteMessage,
)
from google.protobuf import text_format

LOG = logging.getLogger(__name__)

_orig_handle = RemoteProtocol._handle_message


def _patched_handle(self: RemoteProtocol, raw_msg: bytes) -> None:
    _orig_handle(self, raw_msg)
    hook: Callable[[RemoteMessage], None] | None = getattr(self, "hm_ime_hook", None)
    if not hook:
        return
    try:
        msg = RemoteMessage()
        msg.ParseFromString(raw_msg)
        kinds = {f.name for f, _ in msg.ListFields()}
        if kinds & {"remote_ime_show_request", "remote_ime_batch_edit", "remote_ime_key_inject"}:
            LOG.info("IME z TV: %s", text_format.MessageToString(msg, as_one_line=True))
            hook(msg)
    except Exception:  # nikdy nerozbít zpracování ostatních zpráv
        LOG.exception("IME: chyba při zpracování zprávy")


RemoteProtocol._handle_message = _patched_handle  # type: ignore[method-assign]


class Remote(AndroidTVRemote):
    """AndroidTVRemote + správné čítače IME, stav textového pole na TV a vkládání textu."""

    def __init__(self, *args: Any, ime_callback: Callable[[dict[str, Any]], None] | None = None, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self._ime_callback = ime_callback
        self.ime_counter = 0
        self.field_counter = 0

    async def async_connect(self) -> None:
        await super().async_connect()
        proto = self._remote_message_protocol
        if proto is not None:
            proto.hm_ime_hook = self._on_ime  # type: ignore[attr-defined]

    def _emit(self, ev: dict[str, Any]) -> None:
        if self._ime_callback:
            self._ime_callback(ev)

    def _on_ime(self, msg: RemoteMessage) -> None:
        if msg.HasField("remote_ime_key_inject"):
            inj = msg.remote_ime_key_inject
            if inj.HasField("app_info") and inj.app_info.counter:
                self.ime_counter = inj.app_info.counter
            if inj.HasField("text_field_status"):
                st = inj.text_field_status
                if st.counter_field:
                    self.field_counter = st.counter_field
                self._emit({"event": "open", "value": st.value, "label": st.label or inj.app_info.label})
            else:
                # jen změna aplikace, žádné systémové pole -> staré čítače neplatí
                self._reset_counters()
        elif msg.HasField("remote_ime_show_request"):
            st = msg.remote_ime_show_request.remote_text_field_status
            if st.counter_field:
                self.field_counter = st.counter_field
            self._emit({"event": "echo", "value": st.value, "label": st.label})
        elif msg.HasField("remote_ime_batch_edit"):
            if msg.remote_ime_batch_edit.ime_counter == 0:
                self._reset_counters()
                self._emit({"event": "close"})

    def _reset_counters(self) -> None:
        """Aplikace s vlastní klávesnicí (např. Netflix) přijímají text jen s čítači 0 –
        čítače ze zavřeného systémového pole by je zahodily (ověřeno na Philips 55PUS8818)."""
        self.ime_counter = 0
        self.field_counter = 0

    def _proto(self) -> RemoteProtocol:
        proto = self._remote_message_protocol
        if proto is None:
            raise ConnectionClosed("TV není připojena")
        return proto

    def insert_text(self, text: str) -> None:
        """Vloží `text` na pozici kurzoru v aktivním textovém poli TV."""
        if not text:
            return
        proto = self._proto()
        pos = len(text) - 1
        msg = RemoteMessage()
        msg.remote_ime_batch_edit.CopyFrom(
            RemoteImeBatchEdit(
                ime_counter=self.ime_counter,
                field_counter=self.field_counter,
                edit_info=[RemoteEditInfo(insert=1, text_field_status=RemoteImeObject(start=pos, end=pos, value=text))],
            )
        )
        LOG.info("IME na TV: %s", text_format.MessageToString(msg, as_one_line=True))
        proto._reset_idle_disconnect_task()  # noqa: SLF001
        proto._send_message(msg)  # noqa: SLF001
