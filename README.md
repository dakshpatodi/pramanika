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
uvicorn app.main:app --reload
```

Visit **http://localhost:8000** and you should see:

```json
{ "status": "healthy", "message": "Pramanika API Running" }
```

Interactive API docs are auto-generated at **http://localhost:8000/docs**.

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

## 8. What's Intentionally Not Here Yet

- User authentication / accounts
- Payment integration
- Product, category, cart, and order database models
- Real product photography (icons are used as placeholders)
- Any API endpoint beyond the health check

These are all planned for subsequent phases, building on top of this
foundation without needing to restructure what's already here.
