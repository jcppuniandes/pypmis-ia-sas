# Authorized governed reconstruction

On 16 October 2026 (America/Bogota), the human user answered:

> Autorizo reconstrucción gobernada en una base persistente

This explicitly changes the previous requirement to reuse the lost PostgreSQL
Tenant4 / Project16 chain. The new isolated database may create a replacement
chain through actual authorized business lifecycles. It must record its new
identities and must not claim to be the original database or stitch previous
proof into new results. No terminal READY/FROZEN/FID state replay from JSON,
no policy downgrade, no fabricated providers and no operational data writes.

The old blocked reports, manifests and stopped tmpfs containers are retained.
The new Compose project is `pypmis-strategic-persistent-uat`; its PostgreSQL
uses a dedicated named volume, never `pypmis-ia-sas_postgres_data`. Backups
are written as PostgreSQL custom-format dumps into the new private QA folder.
The authorization is for UAT reconstruction, not production investment approval
or human business UAT sign-off.
