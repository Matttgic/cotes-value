"""Socle commun des connecteurs WebSocket (audit du 20/11/2026) : aucune attente sans limite.

``recv_str`` de curl_cffi attend sans fin une trame qui n'arrive pas : le budget du cycle tuait alors la lecture et
tout ce qui était lu était perdu (Winamax, 23-25/10/2026). ``recevoir`` borne chaque trame par une heure de fin.
"""
from __future__ import annotations

import select
import time


def recevoir(ws, fin: float) -> str:
    """Une trame texte, au plus tard à ``fin`` (horloge ``time.monotonic``), sinon ``TimeoutError``.

    Même assemblage que ``WebSocket.recv`` de curl_cffi, mais l'attente est bornée. Les doublures de test n'ont
    que ``recv_str``."""
    fragment = getattr(ws, "recv_fragment", None)
    if fragment is None:
        return ws.recv_str()
    from curl_cffi import CurlECode, CurlError, CurlInfo, CurlWsFlag
    prise = ws.curl.getinfo(CurlInfo.ACTIVESOCKET)
    morceaux = []
    while True:
        try:
            morceau, trame = fragment()
        except CurlError as e:
            if e.code != CurlECode.AGAIN:
                raise
            reste = fin - time.monotonic()
            if reste <= 0:
                raise TimeoutError("délai") from None
            select.select([prise], [], [], min(0.5, reste))
            continue
        if trame.flags & (CurlWsFlag.PING | CurlWsFlag.PONG):
            continue
        if trame.flags & CurlWsFlag.CLOSE:
            raise OSError("fermeture")
        morceaux.append(morceau)
        if trame.bytesleft == 0 and not trame.flags & CurlWsFlag.CONT:
            return b"".join(morceaux).decode("utf-8")
        if time.monotonic() >= fin:
            raise TimeoutError("délai")


def fin_lecture(lecture_s: float, echeance=None) -> float:
    """Heure de fin (``time.monotonic``) d'une demande : ``lecture_s`` au plus, jamais au-delà de l'échéance."""
    reste = echeance.reste() if echeance is not None and hasattr(echeance, "reste") else None
    return time.monotonic() + (lecture_s if reste is None else max(0.0, min(lecture_s, reste)))
