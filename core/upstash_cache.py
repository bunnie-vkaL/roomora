"""Small, fail-open cache client for Upstash Redis REST.

The application must remain usable when the cache is unavailable. Values are
signed before pickling so a corrupted or tampered cache entry is discarded
instead of being unpickled.
"""

import base64
import pickle
import threading
import time

import httpx
from django.conf import settings
from django.core.signing import BadSignature, Signer


_local = {}
_lock = threading.Lock()
_LOCAL_MAX_ITEMS = 256


def _enabled():
    return bool(settings.UPSTASH_REDIS_REST_URL and settings.UPSTASH_REDIS_REST_TOKEN)


def _signed(value):
    payload = base64.b64encode(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)).decode("ascii")
    return Signer().sign(payload)


def _unsigned(value):
    payload = Signer().unsign(value)
    return pickle.loads(base64.b64decode(payload.encode("ascii")))


def _remote(command):
    if not _enabled():
        return None
    try:
        response = httpx.post(
            settings.UPSTASH_REDIS_REST_URL.rstrip("/") + "/pipeline",
            headers={"Authorization": f"Bearer {settings.UPSTASH_REDIS_REST_TOKEN}"},
            json=[command],
            timeout=settings.UPSTASH_REDIS_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()[0].get("result")
    except (httpx.HTTPError, ValueError, IndexError, TypeError):
        return None


def get(key):
    if not _enabled():
        return None
    now = time.monotonic()
    with _lock:
        entry = _local.get(key)
        if entry and entry[0] > now:
            return entry[1]
        _local.pop(key, None)

    raw = _remote(["GET", key])
    if not raw:
        return None
    try:
        value = _unsigned(raw)
    except (BadSignature, ValueError, TypeError, pickle.UnpicklingError, EOFError):
        return None
    with _lock:
        if len(_local) >= _LOCAL_MAX_ITEMS:
            _local.pop(next(iter(_local)))
        _local[key] = (now + settings.UPSTASH_LOCAL_TTL, value)
    return value


def set(key, value, ttl=None):
    if not _enabled():
        return
    ttl = ttl or settings.UPSTASH_CACHE_TTL
    raw = _signed(value)
    _remote(["SET", key, raw, "EX", int(ttl)])
    with _lock:
        if len(_local) >= _LOCAL_MAX_ITEMS:
            _local.pop(next(iter(_local)))
        _local[key] = (time.monotonic() + min(ttl, settings.UPSTASH_LOCAL_TTL), value)
