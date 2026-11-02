"""Mémo des sélections pendant une construction du site.

Le site calcule tout deux fois : à mises fixes, puis sur des copies des paris misées en Kelly (seuls ``mise`` et
``gain`` changent). Les sélecteurs ne lisent ni la mise ni le gain : la seconde passe retrouve exactement les
mêmes sélections. Le mémo les indexe sur le contenu, pas sur les objets : la fonction, la suite des identifiants
stables des paris (champ ``id``) et les arguments, où les ensembles d'``id()`` sont traduits en identifiants.
Le résultat est retraduit vers les objets de la liste reçue, dans des conteneurs neufs (l'appelant peut les
modifier sans toucher au mémo).

Actif seulement dans ``memoriser_selections()`` (site_web.construire) : le cycle, les notifications et les tests
appellent les sélecteurs sans cache. Une liste sans identifiants uniques, ou un argument non traduisible, est
calculée directement.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from functools import wraps

_CACHE: dict | None = None


class _NonMemorisable(Exception):
    pass


@contextmanager
def memoriser_selections():
    global _CACHE
    precedent, _CACHE = _CACHE, {}
    try:
        yield
    finally:
        _CACHE = precedent


def _identifiants(paris) -> tuple[tuple, dict[int, str], dict[str, dict]]:
    if not isinstance(paris, list):
        raise _NonMemorisable
    pids, vers_pid, vers_objet = [], {}, {}
    for p in paris:
        pid = p.get("id") if isinstance(p, dict) else None
        if not isinstance(pid, str) or not pid or pid in vers_objet:
            raise _NonMemorisable
        pids.append(pid)
        vers_pid[id(p)] = pid
        vers_objet[pid] = p
    return tuple(pids), vers_pid, vers_objet


def _cle(v, vers_pid):
    """Argument -> clé hachable ; ensembles et clés de dictionnaire d'id() traduits en identifiants."""
    if isinstance(v, (set, frozenset)):
        if v and all(type(x) is int for x in v):
            try:
                return ("ids", frozenset(vers_pid[x] for x in v))
            except KeyError:
                raise _NonMemorisable from None
        return ("ens", frozenset(v))
    if isinstance(v, dict):
        return ("dict", tuple((k, _cle(x, vers_pid)) for k, x in v.items()))
    if isinstance(v, (list, tuple)):
        return (type(v).__name__, tuple(_cle(x, vers_pid) for x in v))
    try:
        hash(v)
    except TypeError:
        raise _NonMemorisable from None
    return ("val", v)


_IMMUABLES = (str, int, float, bool, type(None), datetime, date)


def _figer(r, vers_pid):
    """Résultat -> forme indépendante des objets (identifiants stables). Types exacts seulement : un ``Counter``
    ou un objet inconnu ne serait pas rendu à l'identique, la fonction est alors calculée sans mémo."""
    if type(r) in (set, frozenset):
        if r and all(type(x) is int for x in r):
            try:
                return ("ids", frozenset(vers_pid[x] for x in r))
            except KeyError:
                raise _NonMemorisable from None
        return ("ens", type(r), frozenset(r))
    if type(r) is dict:
        if r and all(type(k) is int for k in r):
            try:
                return ("dict_ids", tuple((vers_pid[k], _figer(x, vers_pid)) for k, x in r.items()))
            except KeyError:
                raise _NonMemorisable from None
        return ("dict", tuple((k, _figer(x, vers_pid)) for k, x in r.items()))
    if type(r) is list:
        if r and all(type(x) is dict for x in r):
            try:
                return ("objets", tuple(vers_pid[id(x)] for x in r))
            except KeyError:
                raise _NonMemorisable from None
        return ("liste", tuple(_figer(x, vers_pid) for x in r))
    if type(r) is tuple:
        return ("tuple", tuple(_figer(x, vers_pid) for x in r))
    if type(r) in _IMMUABLES:
        return ("val", r)
    raise _NonMemorisable


def _rendre(f, vers_objet):
    """Forme figée -> résultat pour les objets de la liste reçue, dans des conteneurs neufs."""
    genre = f[0]
    if genre == "ids":
        return {id(vers_objet[pid]) for pid in f[1]}
    if genre == "ens":
        return f[1](f[2])
    if genre == "dict_ids":
        return {id(vers_objet[pid]): _rendre(x, vers_objet) for pid, x in f[1]}
    if genre == "dict":
        return {k: _rendre(x, vers_objet) for k, x in f[1]}
    if genre == "objets":
        return [vers_objet[pid] for pid in f[1]]
    if genre == "liste":
        return [_rendre(x, vers_objet) for x in f[1]]
    if genre == "tuple":
        return tuple(_rendre(x, vers_objet) for x in f[1])
    return f[1]


def memoriser(fonction):
    """Décorateur pour un sélecteur ``fonction(paris, *args, **kwargs)`` pur, qui ne lit ni mise ni gain."""
    @wraps(fonction)
    def memorisee(paris, *args, **kwargs):
        cache = _CACHE
        if cache is None:
            return fonction(paris, *args, **kwargs)
        try:
            pids, vers_pid, vers_objet = _identifiants(paris)
            cle = (memorisee, pids, _cle(args, vers_pid), _cle(tuple(sorted(kwargs.items())), vers_pid))
            hash(cle)
        except (_NonMemorisable, TypeError):
            return fonction(paris, *args, **kwargs)
        if cle not in cache:
            resultat = fonction(paris, *args, **kwargs)
            try:
                cache[cle] = _figer(resultat, vers_pid)
            except _NonMemorisable:
                return resultat
        return _rendre(cache[cle], vers_objet)
    return memorisee
