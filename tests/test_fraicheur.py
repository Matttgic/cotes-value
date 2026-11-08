"""Âge source, réception et relance : aucun réseau, horloge injectée."""
from datetime import datetime, timezone

from cotes.fraicheur import (
    age_depuis_millisecondes, age_epoch_secondes, age_mouvement_s, derniere_observation,
    horodatage_source, resume_lignes,
)

RECU = "2026-10-30T08:00:00+00:00"
NOW = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)


def _ligne(**k):
    return {"match_id": "m", "cle_marche": "c", "marche": "VAINQUEUR", "periode": "MATCH",
            "ligne": None, "issue": "DOM", "joueur": None, "collecte": RECU, **k}


def test_heure_source_absente_ou_naive_reste_inconnue():
    assert horodatage_source(None) is None
    assert horodatage_source("") is None
    assert horodatage_source("  ") is None
    assert horodatage_source("2026-10-30T08:00:00") is None          # sans fuseau
    assert horodatage_source("2026-10-30") is None
    assert horodatage_source(1_761_800_000) is None                  # epoch : unité non établie ici
    assert horodatage_source(1_761_800_000_000) is None              # millisecondes non devinées
    assert horodatage_source(True) is None
    assert horodatage_source("pas une date") is None
    assert age_mouvement_s(None, RECU) is None
    assert age_mouvement_s(RECU, None) is None


def test_fuseau_et_bornes_y_compris_le_zero_reel():
    assert horodatage_source("  2026-10-30T10:00:00+02:00 ") == "2026-10-30T08:00:00+00:00"
    assert age_mouvement_s("2026-10-30T09:00:00+01:00", "2026-10-30T08:05:00Z") == 300
    assert age_mouvement_s("2026-10-30T08:00:00.400Z", RECU) == 0     # même seconde : âge réel
    assert age_mouvement_s("2026-10-30T08:00:01Z", RECU) is None      # future : pas ramenée à 0
    assert age_mouvement_s(datetime(2026, 10, 30, 7, tzinfo=timezone.utc), NOW) == 3600
    assert age_mouvement_s(datetime(2026, 10, 30, 7), NOW) is None    # naïve


def test_resume_ne_remplace_pas_l_absence_par_la_reception():
    r = resume_lignes([
        _ligne(),
        _ligne(maj_source="2026-10-30T07:00:00+00:00"),
        _ligne(maj_bookmaker="hier"),
        _ligne(maj_source="2026-10-30T09:00:00+00:00"),
        _ligne(maj_bookmaker="2026-10-30T06:30:00Z"),
    ])
    assert r["lignes"] == 5
    assert r["source_connue"] == 2
    assert r["source_inconnue"] == 2
    assert r["source_invalide"] == 1
    assert r["mouvement_min_s"] == 3600
    assert r["mouvement_max_s"] == 5400
    assert r["reception"] == RECU


def test_epoch_secondes_sur_l_horloge_injectee_pas_le_mur():
    assert age_epoch_secondes(int(NOW.timestamp()) - 20, NOW) == 20
    assert age_epoch_secondes(int(NOW.timestamp()), NOW) == 0
    assert age_epoch_secondes(int(NOW.timestamp()) + 5, NOW) is None
    assert age_epoch_secondes(int(NOW.timestamp()) * 1000, NOW) is None   # millisecondes : futur
    assert age_epoch_secondes(True, NOW) is None
    assert age_epoch_secondes("20", NOW) == int(NOW.timestamp()) - 20
    assert age_epoch_secondes("non", NOW) is None
    assert age_epoch_secondes(0, datetime(2026, 10, 30, 8, 0)) is None    # maintenant naïf
    # L'horloge figée ignore l'horloge murale : « maintenant » réel est dans le futur de 2020.
    passe = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert age_epoch_secondes(int(datetime.now(timezone.utc).timestamp()), passe) is None


def test_millisecondes_negatives_inconnues_zero_reel_conserve():
    assert age_depuis_millisecondes("4000") == 4
    assert age_depuis_millisecondes("0") == 0
    assert age_depuis_millisecondes("500") == 0                           # sous la seconde, mesuré
    assert age_depuis_millisecondes("-1000") is None
    assert age_depuis_millisecondes("") is None
    assert age_depuis_millisecondes(None) is None
    assert age_depuis_millisecondes(True) is None
    assert age_depuis_millisecondes("abc") is None


def test_meme_observation_remplacee_prix_ulterieur_distinct():
    a = _ligne(achat=1.5)
    identique = _ligne(achat=1.5)
    plus_tard = _ligne(achat=1.8)
    assert derniere_observation([a, identique]) == [identique]
    assert derniere_observation([a, plus_tard]) == [plus_tard]
    assert len(derniere_observation([a, plus_tard])) == 1
    autre = _ligne(issue="EXT", achat=3.2)
    assert [l["issue"] for l in derniere_observation([a, autre, plus_tard])] == ["DOM", "EXT"]
    # Une autre lecture n'est pas dédupliquée contre la précédente.
    assert derniere_observation([plus_tard])[0]["achat"] == 1.8
    assert [l["issue"] for l in derniere_observation([a, {"pas": "une ligne"}, autre])] == ["DOM", "EXT"]
