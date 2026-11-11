import tarfile
from datetime import date

from scripts import archiver_donnees_brutes as A


def _donnees(tmp_path):
    for d in ("cotes", "opportunites"):
        (tmp_path / d).mkdir()
        for jour in ("2026-09-30", "2026-10-01", "2026-10-31", "2026-11-02"):
            (tmp_path / d / f"{jour}.jsonl.gz").write_bytes(f"{d}{jour}".encode())
    (tmp_path / "cotes" / "reprise.json").write_text("{}")          # ignoré : pas un jour
    return tmp_path


def test_seuls_les_mois_termines_depuis_30_jours(tmp_path):
    d = _donnees(tmp_path)
    assert list(A.mois_archivables(d, date(2026, 11, 11))) == ["2026-09"]
    plan = A.mois_archivables(d, date(2026, 12, 5))
    assert list(plan) == ["2026-09", "2026-10"]
    assert plan["2026-10"] == ["cotes/2026-10-01.jsonl.gz", "cotes/2026-10-31.jsonl.gz",
                               "opportunites/2026-10-01.jsonl.gz", "opportunites/2026-10-31.jsonl.gz"]


def test_emballer_puis_verifier(tmp_path):
    (tmp_path / "d").mkdir()
    d = _donnees(tmp_path / "d")
    plan = A.mois_archivables(d, date(2026, 12, 5))
    tar, man = A.emballer(d, "2026-10", plan["2026-10"], tmp_path / "s")
    assert A.verifier(tar, man) == []
    with tarfile.open(tar) as t:
        assert t.extractfile("cotes/2026-10-01.jsonl.gz").read() == b"cotes2026-10-01"
    # un octet changé dans le manifeste : refusé
    man.write_text(man.read_text().replace(plan["2026-10"][0], "cotes/autre.jsonl.gz"))
    assert A.verifier(tar, man)


def test_essai_a_blanc_n_ecrit_rien(tmp_path, capsys):
    d = _donnees(tmp_path)
    assert A.main([str(d), "--aujourdhui", "2026-12-05"]) == 0
    assert "2026-10 : 4 fichiers" in capsys.readouterr().out
    assert sorted(p.name for p in d.iterdir()) == ["cotes", "opportunites"]
