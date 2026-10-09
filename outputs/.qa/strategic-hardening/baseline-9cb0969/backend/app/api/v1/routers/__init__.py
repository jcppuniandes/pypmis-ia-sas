"""Per-domain FastAPI routers for the API v1 surface.

The top-level :mod:`app.api.v1.router` aggregates these sub-routers via
``include_router`` calls. New endpoints should land in (or motivate) a
domain-specific router here rather than the historical monolithic file.
"""
