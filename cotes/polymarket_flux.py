"""Flux en direct des carnets Polymarket (websocket CLOB), pour le serveur en direct.

Processus à part, lancé par scripts/serveur_direct.py : ``python -m cotes.polymarket_flux --dossier <dossier>``.
- ``polymarket.collecter`` écrit dans le dossier la liste des jetons suivis (``jetons.json``) : un jeton par marché,
  celui de la 1re issue, dont gamma donne bestBid / bestAsk ;
- le flux s'abonne à ces jetons, tient chaque carnet à jour (message « book » = image complète, « price_change » =
  variations) et écrit toutes les ``ECRITURE_S`` secondes le meilleur achat / vente de chaque jeton (``prix.json``) ;
- au cycle suivant, ``polymarket.collecter`` remplace le prix de gamma par celui du flux s'il est plus récent.
Coupure : reconnexion avec attente croissante (1 s à 60 s) ; une nouvelle connexion repart des images « book ».
Ne lève jamais : sans flux, gamma reste la seule lecture.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
JETONS = "jetons.json"
PRIX = "prix.json"
ECRITURE_S = 2.0
PING_S = 10.0
RELECTURE_JETONS_S = 60.0
SILENCE_MAX_S = 30.0           # aucune donnée ni PONG pendant ce temps : connexion reprise
AGE_MAX_S = 30.0               # fichier de prix plus vieux (flux arrêté) : ignoré par la collecte
PAQUET = 500                   # jetons par message d'abonnement


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _nombre(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _ecrire_json(chemin: Path, contenu) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(contenu, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, chemin)


def _lire_json(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


# --- côté collecte -------------------------------------------------------------------------------------------------

def dossier() -> Path | None:
    """Dossier du flux (variable ``POLYMARKET_FLUX``), ou None : flux inactif."""
    d = os.environ.get("POLYMARKET_FLUX", "").strip()
    return Path(d) if d and d.lower() not in ("non", "off") else None


def ecrire_jetons(jetons: list[str], d: Path | None = None) -> None:
    d = d or dossier()
    if d is None:
        return
    try:
        _ecrire_json(d / JETONS, sorted(set(jetons)))
    except OSError:
        pass


def prix_frais(d: Path | None = None, maintenant: datetime | None = None,
               age_max_s: float = AGE_MAX_S) -> dict[str, tuple[float, float, datetime]]:
    """{jeton: (achat, vente, heure)}. Tant que la connexion vit, un carnet reçu reste exact même sans variation :
    l'heure est celle de la dernière écriture du flux (toutes les ``ECRITURE_S`` s). Fichier plus vieux que
    ``age_max_s`` (flux arrêté) : rien."""
    d = d or dossier()
    if d is None:
        return {}
    maintenant = maintenant or _maintenant()
    contenu = _lire_json(d / PRIX, {})
    try:
        maj = datetime.fromisoformat(contenu["maj"])
    except (TypeError, KeyError, ValueError):
        return {}
    if not 0 <= (maintenant - maj).total_seconds() <= age_max_s:
        return {}
    out = {}
    for jeton, v in (contenu.get("prix") or {}).items():
        try:
            bid, ask = float(v[0]), float(v[1])
        except (TypeError, ValueError, IndexError):
            continue
        out[jeton] = (bid, ask, maj)
    return out


# --- côté flux -----------------------------------------------------------------------------------------------------

class Carnets:
    """Carnets par jeton : {prix: taille} à l'achat et à la vente, heure de la dernière variation."""

    def __init__(self):
        self.achats: dict[str, dict[float, float]] = {}
        self.ventes: dict[str, dict[float, float]] = {}
        self.heure: dict[str, datetime] = {}

    def _poser(self, jeton: str, cote: str, prix, taille) -> None:
        p, s = _nombre(prix), _nombre(taille)
        if jeton is None or p is None or s is None:
            return
        livre = (self.achats if cote in ("BUY", "bids") else self.ventes).setdefault(jeton, {})
        if s <= 0:
            livre.pop(p, None)
        else:
            livre[p] = s

    def appliquer(self, message, quand: datetime | None = None) -> int:
        """Applique un message (objet ou liste d'objets). Renvoie le nombre de jetons touchés."""
        quand = quand or _maintenant()
        if isinstance(message, list):
            return sum(self.appliquer(m, quand) for m in message)
        if not isinstance(message, dict):
            return 0
        genre = message.get("event_type")
        if genre == "book":
            jeton = str(message.get("asset_id") or "")
            if not jeton:
                return 0
            self.achats[jeton], self.ventes[jeton] = {}, {}
            for cote in ("bids", "asks"):
                for niveau in message.get(cote) or message.get("buys" if cote == "bids" else "sells") or []:
                    if isinstance(niveau, dict):
                        self._poser(jeton, cote, niveau.get("price"), niveau.get("size"))
            self.heure[jeton] = quand
            return 1
        if genre == "price_change":
            touches = set()
            # format actuel : price_changes[] avec asset_id ; ancien : asset_id + changes[]
            for c in message.get("price_changes") or []:
                if isinstance(c, dict) and c.get("asset_id"):
                    j = str(c["asset_id"])
                    self._poser(j, str(c.get("side") or "").upper(), c.get("price"), c.get("size"))
                    touches.add(j)
            if message.get("asset_id"):
                j = str(message["asset_id"])
                for c in message.get("changes") or []:
                    if isinstance(c, dict):
                        self._poser(j, str(c.get("side") or "").upper(), c.get("price"), c.get("size"))
                touches.add(j)
            for j in touches:
                self.heure[j] = quand
            return len(touches)
        return 0

    def meilleurs(self) -> dict[str, list]:
        """{jeton: [achat, vente, heure ISO]} des carnets à deux côtés cohérents."""
        out = {}
        for jeton, t in self.heure.items():
            achats, ventes = self.achats.get(jeton) or {}, self.ventes.get(jeton) or {}
            if not achats or not ventes:
                continue
            bid, ask = max(achats), min(ventes)
            if 0 < bid <= ask < 1:
                out[jeton] = [bid, ask, t.isoformat(timespec="seconds")]
        return out


def _journal(message: str) -> None:
    print(f"{_maintenant().isoformat(timespec='seconds')} polymarket_flux : {message}", flush=True)


def _est_delai(e: Exception) -> bool:
    return "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower()


def _session(d: Path, jetons: list[str], connecter, arret) -> None:
    """Une connexion : abonnement, lecture, écriture régulière. Revient à la coupure ou au changement de jetons."""
    ws = connecter(URL)
    try:
        for i in range(0, len(jetons), PAQUET):
            ws.send_str(json.dumps({"type": "market", "assets_ids": jetons[i:i + PAQUET]}))
        carnets = Carnets()
        ping = ecrit = relu = derniere_donnee = time.monotonic()
        vu = _maintenant()             # heure du dernier message ou PONG : le carnet est sûr jusque-là
        while not arret():
            maintenant = time.monotonic()
            if maintenant - ping >= PING_S:
                ws.send_str("PING")
                ping = maintenant
            if maintenant - ecrit >= ECRITURE_S:
                _ecrire_json(d / PRIX, {"maj": vu.isoformat(timespec="seconds"), "prix": carnets.meilleurs()})
                ecrit = maintenant
            if maintenant - relu >= RELECTURE_JETONS_S:
                relu = maintenant
                if sorted(_lire_json(d / JETONS, [])) != jetons:
                    _journal("liste de jetons changée : nouvel abonnement")
                    return
            if maintenant - derniere_donnee >= SILENCE_MAX_S:
                raise ConnectionError(f"aucune donnée depuis {SILENCE_MAX_S:g} s")
            try:
                brut, _ = ws.recv(timeout=1.0)
            except Exception as e:  # noqa: BLE001
                if _est_delai(e):
                    continue
                raise
            texte = brut.decode("utf-8", "replace") if isinstance(brut, bytes) else str(brut)
            derniere_donnee, vu = time.monotonic(), _maintenant()
            if not texte or texte == "PONG":
                continue
            try:
                message = json.loads(texte)
            except ValueError:
                continue
            carnets.appliquer(message)
    finally:
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass


def _connecter_curl(url: str):
    from curl_cffi.requests import Session
    return Session().ws_connect(url, timeout=15)


def boucle(d: Path, connecter=_connecter_curl, arret=lambda: False, attendre=time.sleep) -> None:
    attente = 1.0
    while not arret():
        jetons = sorted(_lire_json(d / JETONS, []))
        if not jetons:
            attendre(10)
            continue
        debut = time.monotonic()
        try:
            _journal(f"connexion, {len(jetons)} jetons")
            _session(d, jetons, connecter, arret)
        except Exception as e:  # noqa: BLE001 - le flux ne tombe jamais
            _journal(f"coupure : {type(e).__name__}: {str(e)[:120]}")
        attente = 1.0 if time.monotonic() - debut > 120 else min(60.0, attente * 2)
        if not arret():
            attendre(attente)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dossier", required=True)
    d = Path(parser.parse_args().dossier)
    d.mkdir(parents=True, exist_ok=True)
    try:
        boucle(d)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
