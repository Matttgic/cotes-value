"""Transmet le flux public à l'expéditeur, authentifié par l'identité GitHub Actions.

Aucune clé Web Push ou donnée d'abonnement n'est nécessaire dans GitHub.
Une panne de notification ne doit pas interrompre la collecte ni le règlement.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.notifications import API  # noqa: E402


def transmettre(flux: dict, env=None, ouvrir=urlopen) -> dict:
    env = os.environ if env is None else env
    url = env.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    credential = env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url.startswith("https://") or not credential:
        return {"ok": False, "erreur": "Identité GitHub Actions indisponible"}
    try:
        sep = "&" if "?" in url else "?"
        requete = Request(url + sep + urlencode({"audience": "cotes-value-notifications"}),
                          headers={"Authorization": f"Bearer {credential}"})
        with ouvrir(requete, timeout=20) as r:
            token = json.load(r).get("value")
        if not isinstance(token, str) or not token:
            return {"ok": False, "erreur": "Identité GitHub invalide"}
        requete = Request(API + "/dispatch", data=json.dumps(flux, ensure_ascii=False).encode(),
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with ouvrir(requete, timeout=60) as r:
            d = json.load(r)
        # Liste blanche : ne jamais imprimer des jetons ou abonnements renvoyés par erreur.
        return {k: d[k] for k in ("ok", "sent", "expired", "failed", "devices") if k in d}
    except HTTPError as e:
        return {"ok": False, "erreur": f"Service notifications HTTP {e.code}"}
    except (URLError, OSError, ValueError, TypeError):
        return {"ok": False, "erreur": "Service notifications indisponible"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--flux", type=Path, default=Path("site/notifications.json"))
    args = p.parse_args()
    bilan = transmettre(json.loads(args.flux.read_text(encoding="utf-8")))
    print(json.dumps(bilan, ensure_ascii=False))
    sys.exit(0 if bilan.get("ok") else 1)
