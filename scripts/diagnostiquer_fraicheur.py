"""Diagnostic local, sans reseau et sans modification des donnees d'origine."""
from __future__ import annotations
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"

def instant(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None

def nombre(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None

def examiner(row, now, seuil_s=60):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("maintenant doit avoir un fuseau")
    if nombre(seuil_s) is None or seuil_s <= 0:
        raise ValueError("seuil strictement positif requis")
    source = str(row.get("source") or row.get("bookmaker") or "inconnue")
    pin = "pinnacle" in source.lower()
    result = {"source": source, "sport": row.get("sport"),
              "marche": row.get("marche"), "periode": row.get("periode"),
              "match_id": row.get("match_id"), "age_observation_s": None,
              "age_cache_estime_s": None, "observation_dans_objectif": False,
              "observation_et_cache_dans_objectif": False,
              "prix_amont_verifie": False}
    received = instant(row.get("collecte_recue")) or instant(row.get("collecte"))
    started = instant(row.get("collecte_debut"))
    if received is None:
        result["statut"] = "horodatage_invalide"
        return result
    age = (now - received).total_seconds()
    if age < 0 or (started is not None and started > received):
        result["statut"] = "horloge_incoherente"
        return result
    result["age_observation_s"] = round(age, 3)
    result["observation_dans_objectif"] = age <= seuil_s
    cache = nombre(row.get("age_cache_s"))
    if cache is not None:
        elapsed = (now - started).total_seconds() if started else age
        result["age_cache_estime_s"] = round(cache + elapsed, 3)
    raw_status = str(row.get("status") or row.get("statut") or "").lower()
    if row.get("suspendue") is True or raw_status in {"suspended", "suspendu", "suspendue", "closed", "ferme", "fermée"}:
        status = "suspendue"
    elif row.get("cote_perimee") is True:
        status = "perimee_signalee"
    elif age > seuil_s:
        status = "observation_ancienne"
    elif "age_cache_s" in row and row.get("age_cache_s") is not None and cache is None:
        status = "age_cache_invalide"
    elif cache is None:
        status = "cache_inconnu_pinnacle" if pin else "observation_recente_age_source_inconnu"
    elif result["age_cache_estime_s"] > seuil_s:
        status = "cache_ancien"
    else:
        status = "observation_recente_cache_documente"
        result["observation_et_cache_dans_objectif"] = True
    result["statut"] = status
    return result

def mediane(values):
    if not values:
        return None
    vals = sorted(values)
    n = len(vals)
    return round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2, 3)

def p95(values):
    if not values:
        return None
    vals = sorted(values)
    return round(vals[max(0, math.ceil(.95 * len(vals)) - 1)], 3)

def resumer(rows, now, seuil_s=60):
    groups = defaultdict(list)
    invalides = 0
    for row in rows:
        if not isinstance(row, dict):
            invalides += 1
            continue
        item = examiner(row, now, seuil_s)
        groups[(item["source"], item["sport"], item["marche"], item["periode"])].append(item)
    summaries = []
    for key, items in sorted(groups.items(), key=lambda pair: tuple(str(v) for v in pair[0])):
        ages = [it["age_observation_s"] for it in items if it["age_observation_s"] is not None]
        cache_ages = [it["age_cache_estime_s"] for it in items if it["age_cache_estime_s"] is not None]
        summaries.append(dict(zip(("source", "sport", "marche", "periode"), key)) | {
            "lignes": len(items), "matchs_distincts": len({str(it["match_id"]) for it in items if it["match_id"] is not None}),
            "observations_dans_objectif": sum(it["observation_dans_objectif"] for it in items),
            "observation_et_cache_dans_objectif": sum(it["observation_et_cache_dans_objectif"] for it in items),
            "age_observation_p50_s": mediane(ages), "age_observation_p95_s": p95(ages),
            "age_observation_max_s": max(ages) if ages else None,
            "age_cache_estime_max_s": max(cache_ages) if cache_ages else None,
            "statuts": dict(Counter(it["statut"] for it in items))})
    return {"version": VERSION, "evalue_a": now.isoformat(), "seuil_s": seuil_s,
            "objets_non_lignes": invalides, "groupes": summaries,
            "limites": ["Aucun taux d'exhaustivite sans inventaire attendu independant.",
                        "Age HTTP de cache ne prouve pas l'age du prix chez le bookmaker.",
                        "Un export partiel ne represente pas toutes les sources.",
                        "Diagnostic uniquement : aucun filtre du moteur n'est modifie."]}

def charger(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(doc, list):
        return doc
    if not isinstance(doc, dict):
        raise ValueError("Liste JSON ou objet contenant des lignes attendu")
    if isinstance(doc.get("lignes"), list):
        return doc["lignes"]
    rows = []
    for block in doc.values():
        if isinstance(block, dict) and isinstance(block.get("lignes"), list):
            rows.extend(block["lignes"])
    if not rows:
        raise ValueError("Aucune ligne trouvee : utiliser un export brut, pas etat.json ou paris.json")
    return rows

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exports", nargs="+", help="JSON de lignes, horizon_direct.json ou cache de lignes")
    parser.add_argument("--maintenant", help="Instant ISO avec fuseau ; omettre pour l'heure courante")
    parser.add_argument("--seuil-s", type=float, default=60)
    parser.add_argument("--sortie", required=True, help="Nouveau dossier pour rapport.json et rapport.csv")
    args = parser.parse_args()
    now = instant(args.maintenant) if args.maintenant else datetime.now(timezone.utc)
    if now is None:
        parser.error("--maintenant invalide ou sans fuseau")
    if nombre(args.seuil_s) is None or args.seuil_s <= 0:
        parser.error("--seuil-s doit etre strictement positif")
    paths = [Path(p).resolve() for p in args.exports]
    if len(paths) != len(set(paths)):
        parser.error("export repete : les fichiers d'entree doivent etre distincts")
    target = Path(args.sortie)
    if target.exists():
        parser.error("le dossier de sortie doit etre nouveau (pas d'ecrasement)")
    try:
        rows = [row for path in paths for row in charger(path)]
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    report = resumer(rows, now, args.seuil_s)
    report["exports"] = [p.name for p in paths]
    target.mkdir(parents=True, exist_ok=False)
    (target / "rapport.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["source", "sport", "marche", "periode", "lignes", "matchs_distincts", "observations_dans_objectif",
              "observation_et_cache_dans_objectif", "age_observation_p50_s", "age_observation_p95_s",
              "age_observation_max_s", "age_cache_estime_max_s", "statuts"]
    with (target / "rapport.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for group in report["groupes"]:
            writer.writerow({**group, "statuts": json.dumps(group["statuts"], ensure_ascii=False)})
    print(json.dumps({"lignes_analysees": len(rows), "groupes": len(report["groupes"]),
                      "rapport": str(target / "rapport.json")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
