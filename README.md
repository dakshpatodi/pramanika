# Pramanika

An e-commerce platform for cereals, ready mixes, millets, flours, pulses, dry fruits,
spices, and healthy foods.

> **Status: Phase 1** - project architecture, tooling, and the homepage UI only.
> There is intentionally **no authentication, no payments, and no business logic**
> yet. Cart, checkout, product APIs, and user accounts arrive in later phases.

---

## 1. Project Overview

Pramanika is a full-stack e-commerce app built as a Next.js (TypeScript)
frontend backed by a FastAPI (Python) service, with PostgreSQL as the eventual
database. Phase 1 establishes:

- A clean, modular project structure for both frontend and backend
- A fully responsive, animated homepage UI with placeholder content
- A FastAPI app with CORS, config, and DB session scaffolding wired up
- A single working endpoint (`GET /`) to confirm the API is reachable
- Alembic migration tooling, ready for Phase 2 once real models are added

No product, cart, or user data is real yet - everything on the homepage is
placeholder content defined in `frontend/src/lib/placeholder-data.ts`.

## 2. Tech Stack

**Frontend**
- Next.js 15 (App Router) + React 19 + TypeScript
- Tailwind CSS
- shadcn/ui conventions (CVA-based `Button`, `Card` primitives)
- Framer Motion (hero entrance + floating illustration animation)
- Lucide React icons

**Backend**
- FastAPI
- SQLAlchemy 2.0 (engine/session only - no models yet)
- Alembic (configured, no migrations yet)
- Pydantic v2 / pydantic-settings
- PostgreSQL (configuration only)

**Tooling**
- Git for version control
- ESLint (flat config) for the frontend
- `.env` based configuration on both sides

## 3. Folder Structure

```
healthy-harvest/
├── frontend/                     # Next.js app
│   ├── src/
│   │   ├── app/                  # App Router: layout, homepage, globals.css, icon
│   │   ├── components/
│   │   │   ├── ui/               # shadcn-style primitives (Button, Card)
│   │   │   ├── layout/            # Navbar, Footer (shared across all pages)
│   │   │   ├── home/              # Homepage sections (Hero, Categories, ...)
│   │   │   └── shared/            # Cross-page reusable pieces (ProductCard, ...)
│   │   ├── lib/                  # cn() helper, icon registry, placeholder data
│   │   ├── hooks/                # UI-only hooks (e.g. useMediaQuery)
│   │   ├── types/                # Shared TypeScript interfaces
│   │   ├── services/             # API client (fetch wrapper)
│   │   └── styles/                # Raw brand color tokens (for non-Tailwind contexts)
│   ├── public/                   # Static assets (empty for now - no real photos yet)
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── components.json           # shadcn/ui CLI config
│
├── backend/                      # FastAPI app
│   ├── app/
│   │   ├── main.py               # App instance, CORS, GET / health check
│   │   ├── core/config.py        # Settings loaded from .env
│   │   ├── database/session.py   # SQLAlchemy engine/session/Base
│   │   ├── models/                # Empty - ORM models start in Phase 2
│   │   ├── schemas/                # Empty - Pydantic DTOs start in Phase 2
│   │   ├── services/               # Empty - business logic starts in Phase 2
│   │   ├── api/                    # Empty - versioned routers start in Phase 2
│   │   └── utils/
│   ├── alembic/                   # Migration environment (no migrations yet)
│   ├── alembic.ini
│   ├── requirements.txt
│   └── .env.example
│
└── docs/                          # Project documentation (this is where
                                    # architecture decisions get recorded
                                    # as the project grows)
```

## 4. Installation

Clone or unzip the project, then set up each side independently.

### Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- PostgreSQL 14+ running locally (or a connection string to a hosted instance)

### Frontend setup

```bash
cd frontend
npm install
cp .env.local.example .env.local
```

### Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` with your real PostgreSQL credentials (or a full
`DATABASE_URL`). No tables are created in Phase 1, so the database only
needs to exist and be reachable - it does not need any schema yet.

## 5. Running the Frontend

```bash
cd frontend
npm run dev
```

Visit **http://localhost:3000** to see the homepage.

## 6. Running the Backend

```bash
cd backend
source venv/bin/activate
**First time only:** apply database migrations before starting the server:
```bash
alembic upgrade head
```
uvicorn app.main:app --reload
```

Visit **http://localhost:8000** and you should see:

```json
{ "status": "healthy", "message": "Pramanika API Running" }
```

Interactive API docs are auto-generated at **http://localhost:8000/docs**.

## Authentication

Phase 2 adds a full JWT-based authentication system on top of the Phase 1
foundation - registration, login, protected routes, and role-based
authorization.

### Setup

Authentication requires two extra one-time steps beyond the base setup:

1. Apply the auth-related database migrations (creates `users`,
   `revoked_tokens`, and adds `last_login`):
```bash
   cd backend
   alembic upgrade head
```
2. Ensure `backend/.env` has the four JWT variables set (see Environment
   Variables above) - the defaults work fine for local development.

### JWT flow

- **Access tokens** (30 min default) are sent as `Authorization: Bearer <token>`
  on every request to a protected route (e.g. `GET /api/users/me`).
- **Refresh tokens** (7 days default) are used only at `POST /api/auth/refresh`
  to obtain a new token pair. Every refresh **rotates** the token: the one
  just used is immediately revoked, so a stolen refresh token is only ever
  usable once.
- **Logout** (`POST /api/auth/logout`) revokes the current refresh token.
  Revoked tokens are tracked in the `revoked_tokens` table by their `jti`
  claim - access tokens are never checked against this table (by design;
  see `app/models/revoked_token.py` for the tradeoff this implies).
- The frontend's Axios client (`frontend/src/lib/axios.ts`) automates all of
  this: it attaches the access token to every request, silently refreshes
  and retries on a `401`, and forces a full logout if the refresh itself fails.

Full request/response examples for every endpoint, a sequence diagram, and a
Postman collection are in [`docs/testing.md`](./docs/testing.md) and
[`docs/postman-collection.json`](./docs/postman-collection.json).

### Endpoints

| Method | Path | Auth required | Description |
|---|---|---|---|
| POST | `/api/auth/register` | No | Create a new customer account |
| POST | `/api/auth/login` | No | Authenticate, receive access + refresh tokens |
| POST | `/api/auth/refresh` | No (refresh token in body) | Rotate to a new token pair |
| POST | `/api/auth/logout` | No (refresh token in body) | Revoke a refresh token |
| GET | `/api/users/me` | Yes (access token) | Get the authenticated user's own profile |

### Frontend pages

| Route | Description |
|---|---|
| `/login` | Email/password login, "remember me", forgot-password placeholder |
| `/register` | Account creation with live password-strength feedback |
| `/profile` | Protected route - name, email, phone, role, status, member since, logout |

## 7. Environment Variables

### `frontend/.env.local`

| Variable | Description | Default |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL of the FastAPI backend | `http://localhost:8000` |

### `backend/.env`

| Variable | Description | Default |
|---|---|---|
| `APP_NAME` | Display name used in API metadata | `Pramanika API` |
| `APP_ENV` | Environment name | `development` |
| `DEBUG` | Enables verbose errors | `true` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000` |
| `POSTGRES_USER` | DB username | `healthy_harvest` |
| `POSTGRES_PASSWORD` | DB password | `changeme` |
| `POSTGRES_HOST` | DB host | `localhost` |
| `POSTGRES_PORT` | DB port | `5432` |
| `POSTGRES_DB` | DB name | `healthy_harvest_db` |
| `DATABASE_URL` | Optional full connection string; overrides the `POSTGRES_*` fields above | *(empty)* |
|`SECRET_KEY` | Signs and verifies JWTs - must be a real random value in production |	(dev placeholder - see .env.example)
|`ALGORITHM` |JWT signing algorithm|	HS256
|`ACCESS_TOKEN_EXPIRE_MINUTES`|	How long an access token stays valid	| 30
|`REFRESH_TOKEN_EXPIRE_DAYS` |	How long a refresh token stays valid before it must be used or re-issued |	7


## 8. What's Intentionally Not Here Yet

- User authentication / accounts
- Payment integration
- Product, category, cart, and order database models
- Real product photography (icons are used as placeholders)
- Any API endpoint beyond the health check

These are all planned for subsequent phases, building on top of this
foundation without needing to restructure what's already here.
