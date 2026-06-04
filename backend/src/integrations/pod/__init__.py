"""POD design platform integration (placeholder).

POD is the upstream design / order-source platform that already shares a JWT
secret with this service (see ``POD_*`` env vars). Future work here will:

- Pull design-side orders / SKU customization metadata into our system.
- Push back cost / production-process / packaging info to POD.

For now this package only registers an empty marker so other code can detect
its presence; the real client will land in a follow-up change.
"""

# Intentionally no client registered yet — see README.md for the planned API surface.
