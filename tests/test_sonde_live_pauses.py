import json

import requests

from scripts.sonde_live_pauses import probe, summarize


def test_score_fige_n_est_pas_une_pause():
    s = summarize([{"live": True, "score": {"home": "0", "away": "0"}, "markets": []}])
    assert s["fields_present"]["matchClock"] == 0
    assert s["pause_detection"].startswith("not_implemented")


def test_sonde_bornee_sans_reessai_ni_fuite_de_cle(monkeypatch):
    monkeypatch.setenv("PULSESCORE_KEY", "secret-test-pulse")
    monkeypatch.setenv("PROPLINE_API_KEY", "secret-test-prop")
    monkeypatch.setattr("scripts.sonde_live_pauses.time.sleep", lambda _: None)
    class Http:
        calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            raise requests.RequestException("secret-test-pulse secret-test-prop")
    http = Http()
    result = probe(http)
    assert result["requests"] == len(http.calls) == 11
    assert not any("secret-test" in url for url, _ in http.calls)
    assert "secret-test" not in json.dumps(result)
    assert all(kwargs["timeout"] == 15 for _, kwargs in http.calls)


def test_sonde_sans_cles_ne_fait_que_les_cinq_get_publics(monkeypatch):
    monkeypatch.delenv("PULSESCORE_KEY", raising=False)
    monkeypatch.delenv("PROPLINE_API_KEY", raising=False)
    class Response:
        status_code = 200
        def json(self):
            return []
    class Http:
        def get(self, *args, **kwargs):
            return Response()
    result = probe(Http())
    assert result["requests"] == 5
    assert "skipped" in result["pulsescore"]
