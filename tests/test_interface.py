"""Contrats du document autonome : navigation, étiquettes et absence d'identifiants dupliqués."""
from collections import Counter
from html.parser import HTMLParser

from scripts.site_web import construire


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.onglets = []
        self.labels = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.append(a["id"])
        if tag == "button" and a.get("data-o"):
            self.onglets.append(a["data-o"])
        if tag == "label" and a.get("for"):
            self.labels.append(a["for"])


def test_document_autonome_navigation_unique_et_apercu(tmp_path):
    html = construire(tmp_path, tmp_path / "site").read_text()
    p = Elements()
    p.feed(html)
    assert not [k for k, n in Counter(p.ids).items() if n > 1]
    # Quatre onglets : « À jouer », Stratégies, Analyses, Segments et À régler vivent sous Paris, Bilan et Santé.
    assert p.onglets == ["paris", "bilan", "notifications", "controle"]
    assert {"strategies-mobile", "fraicheur", "liste-paris"} <= set(p.ids)
    assert set(p.labels) <= set(p.ids)
    # Les fragments servent au routeur, jamais à une ancre située sous les filtres.
    assert not set(p.onglets) & set(p.ids)
    assert "__INTERFACE_" not in html
    assert "function installerActualisation" in html
    assert "function adapterTableaux" in html
    assert (tmp_path / "site/verification-responsive.html").exists()


def test_lignes_compactes_et_toutes_les_references_par_defaut():
    from scripts.site_web import MODELE
    # Les références sont toujours consultables sans changer le filtre initial.
    assert '<option value="" selected>Toutes</option>' in MODELE
    assert '<option value="comparateurs" selected>' not in MODELE
    # Les deux listes principales utilisent un dépliage natif, pas une modale.
    for nom in ('carteParis',):
        debut = MODELE.index('const '+nom)
        bloc = MODELE[debut:MODELE.index('`;', debut)]
        assert '<details class="ligne-detail ligne-pari' in bloc
        assert 'class="pari-selection"' in bloc.split('</summary>')[0]
        assert '</summary><div class="ligne-corps">' in bloc
    assert '"#liste-segments > details"' in MODELE
    assert 'd.ontoggle' in MODELE
    assert 's.presentation !== "lignes-v1"' in MODELE
