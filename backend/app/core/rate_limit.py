"""
Shared rate limiter instance.

Defined in its own module - not inside main.py - so route modules
(app/api/auth.py) can import `limiter` and apply `@limiter.limit(...)`
without creating a circular import with main.py, which needs to
register the same limiter on `app.state` and wire up its exception
handler.

Storage backend: in-memory (the library's default fallback when no
`storage_uri` is given). That's fine for a single dev/prod-lite process,
but it means the counter is per-process - running uvicorn with multiple
workers, or multiple replicas behind a load balancer, would give each
process its own independent 5/minute bucket rather than one shared
limit. If this ever moves to a multi-worker deployment, pass
`storage_uri="redis://..."` here so every process shares one counter.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)