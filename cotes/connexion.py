"""Connexions HTTP réutilisées (keep-alive) pour les sources lues plusieurs fois par cycle.

``requests.get`` ouvre une nouvelle connexion TCP + TLS à chaque appel. Pinnacle (matchups, prix et HEAD de
chaque sport), Polymarket (pages d'événements) et ESPN (un appel par jour et par ligue) gagnent à garder la
connexion ouverte.

Le comportement HTTP reste celui de ``requests.get`` :
- une ``Session`` par fil d'exécution : une ``Session`` n'est pas garantie sûre entre fils, et le cycle lance
  les collecteurs en parallèle ;
- aucun cookie gardé d'une requête à l'autre (``requests.get`` n'en garde pas non plus) : les en-têtes
  envoyés, donc les réponses et le cache Cloudflare, ne changent pas ;
- mêmes arguments (``timeout``, ``headers``, ``allow_redirects``…) et mêmes exceptions ``requests``.
"""
from __future__ import annotations

import http.cookiejar
import threading

import requests


class _AucunCookie(http.cookiejar.DefaultCookiePolicy):
    def set_ok(self, cookie, request):
        return False

    def return_ok(self, cookie, request):
        return False


class Client:
    """``get`` / ``head`` / ``post`` comme ``requests.get`` / ``head`` / ``post``, sur une connexion gardée."""

    def __init__(self) -> None:
        self._local = threading.local()

    def session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.cookies.set_policy(_AucunCookie())
            self._local.session = s
        return s

    def get(self, url, **kwargs):
        return self.session().get(url, **kwargs)

    def head(self, url, **kwargs):
        kwargs.setdefault("allow_redirects", False)      # comme requests.head
        return self.session().head(url, **kwargs)

    def post(self, url, **kwargs):
        return self.session().post(url, **kwargs)
