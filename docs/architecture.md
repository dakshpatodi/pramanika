# Architecture Notes - Phase 1

This file tracks key structural decisions as the project grows. See the
root `README.md` for setup and running instructions.

## Why a separate `frontend/` and `backend/`

Kept as two independent projects (own `package.json` / `requirements.txt`)
rather than a monorepo tool (Turborepo, Nx, etc.). At this stage there's no
shared code between them that would justify the extra tooling - the two
communicate purely over HTTP.

## Frontend

- **App Router, not Pages Router** - it's the actively developed Next.js
  paradigm and supports React Server Components by default.
- **`components/` is split by purpose, not by page**: `ui/` (generic
  primitives), `layout/` (persistent chrome), `home/` (page-specific
  sections), `shared/` (reusable across future pages). This keeps the
  homepage sections easy to find while still promoting reuse.
- **No CSS variable theming** - brand colors are declared directly in
  `tailwind.config.ts` since there's no dark mode or white-labeling
  requirement yet. If that changes, colors should move to CSS custom
  properties and `components.json`'s `cssVariables` flag should flip to `true`.
- **Placeholder data lives in `lib/placeholder-data.ts`**, typed against
  `types/index.ts`. Phase 2 should replace calls to this file with calls to
  `services/api.ts` methods that hit real endpoints, without changing the
  component props those sections already expect.

## Backend

- **Routers are not yet split into `api/v1/...`** because there's only one
  route. `app/main.py` defines `GET /` directly. Once real resources exist,
  add routers under `app/api/` and include them from `main.py` with a
  version prefix (`settings.API_V1_PREFIX` is already defined for this).
- **`Base.metadata` has zero tables.** Alembic is fully wired (env.py reads
  the same `Settings` object the app uses) so the first `alembic revision
  --autogenerate` in Phase 2 will work immediately once models exist and
  are imported in `alembic/env.py`.

## Deferred to later phases

Auth, payments, product/category/cart/order models, and any endpoint
beyond the health check are out of scope for Phase 1 by design - see the
root README's "What's Intentionally Not Here Yet" section.
