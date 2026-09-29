"""Authentication adapters.

Two provider implementations of the ``AuthenticationProvider`` protocol:

- ``dev.py`` — deterministic development stub. Development/testing only.
- ``supabase.py`` — production placeholder (Supabase Auth), not yet wired.

Both return the same domain :class:`~app.domain.models.user.UserContext`. The application
layer must not know which provider produced a context.
"""
