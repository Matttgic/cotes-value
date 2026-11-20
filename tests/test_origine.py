"""Origine de la value à la prise (cotes/origine.py), même définition que l'étude docs/duree-values.md."""
import gzip
import json
from datetime import datetime, timedelta, timezone

from cotes import origine as O
from cotes.alertes.webhook import message_ntfy

T = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
P = {"bookmaker": "PMU", "match_id": "pmu|1", "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None,
     "issue": "DOM", "cote": 2.2, "detecte": T.isoformat()}


def _hist(tmp_path, lignes):
    d = tmp_path / "cotes"
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / "2026-11-20.jsonl.gz", "wt", encoding="utf-8") as f:
        for minutes, c in lignes:
            f.write(json.dumps({"t": (T - timedelta(minutes=minutes)).isoformat(), "b": "PMU", "m": "pmu|1",
                                "k": "RESULTAT_1N2|MATCH||DOM", "c": c}, separators=(",", ":")) + "\n")
        f.write('{"t":"2026-11-20T11:00:00+00:00","b":"PMU","m":"pmu|2","k":"RESULTAT_1N2|MATCH||DOM","c":3.0}\n')


def test_quatre_origines(tmp_path):
    cas = {"stable": [(120, 2.2)], "hausse": [(120, 2.0), (5, 2.2)], "baisse": [(120, 2.4), (5, 2.2)],
           "nouvelle": [(5, 2.2)]}
    for attendu, lignes in cas.items():
        _hist(tmp_path, lignes)
        p = dict(P)
        assert O.annoter(tmp_path, [p], T) == {attendu: 1} and p["origine"] == attendu


def test_cote_absente_de_l_historique(tmp_path):
    _hist(tmp_path, [(30, 1.9)])
    p = dict(P)
    assert O.annoter(tmp_path, [p], T) == {"inconnue": 1} and p["origine"] is None
    assert O.annoter(tmp_path / "rien", [dict(P)], T) == {"inconnue": 1}


def test_ligne_dans_l_alerte():
    a = {"domicile": "A", "exterieur": "B", "debut": "2026-11-20T18:00:00+00:00", "cote": 2.2, "cote_min": 2.1,
         "bookmaker": "PMU", "sport": "football", "selection": "A"}
    assert "monter sa cote" in message_ntfy({**a, "origine": "hausse"})[1]
    assert "Origine" not in message_ntfy(a)[1]
