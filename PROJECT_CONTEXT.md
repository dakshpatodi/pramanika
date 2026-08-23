# Pramanika — Project Context

## Project
Pramanika is an AI-powered e-commerce platform for cereals,
ready mixes, breakfast products, and related food products.

## Current Status

Phase 1 — Project Foundation
Status: COMPLETE

Phase 2 — Authentication
Status: COMPLETE

Phase 3 — Database
Status: IN PROGRESS

## Technology Stack

Frontend:
- Next.js
- React
- TypeScript
- Tailwind CSS

Backend:
- Python
- FastAPI
- SQLAlchemy
- Alembic

Database:
- PostgreSQL
- Docker

Authentication:
- JWT access tokens
- JWT refresh tokens
- Refresh-token rotation
- Logout/revocation
- Protected routes
- Login rate limiting

Development:
- Git
- GitHub
- Postman
- PowerShell

## Git

Main branch:
main

Development branch:
feature/authentication

Phase 2 checkpoint:
phase-2-complete

## Completed Authentication Features

- User registration
- Login
- JWT access token
- JWT refresh token
- Refresh-token rotation
- Logout
- Token revocation
- GET /api/users/me
- Authentication dependencies
- Role-based dependency support
- Login rate limiting
- Frontend login page
- Frontend registration page
- Profile page
- AuthContext
- Protected routes
- Token storage
- Axios API client
- Authentication validation

## Phase 3 — Database

Goal:
Design and implement the e-commerce database.

Planned entities:

- Users — already exists
- Categories
- Products
- Inventory
- Addresses
- Cart
- Cart Items
- Wishlist
- Wishlist Items
- Orders
- Order Items
- Coupons
- Payments
- Reviews

Important:
Do not recreate the existing users table.
Do not break Phase 2 authentication.
Use existing SQLAlchemy/Alembic architecture.
Do not implement Phase 4+ functionality during Phase 3.

## Original Roadmap

Phase 3 — Database
Phase 4 — Product Module
Phase 5 — Shopping Cart
Phase 6 — Checkout
Phase 7 — Razorpay Integration
Phase 8 — User Dashboard
Phase 9 — Admin Dashboard
Phase 10 — AI & Advanced Features
Phase 11 — Deployment

## Planned AI Features

Phase 10 will eventually include:

- AI shopping assistant
- RAG
- Semantic product search
- Product recommendations
- Personalized recommendations
- Frequently bought together

Potential AI stack:
- LLM
- Embeddings
- pgvector
- RAG pipeline

Do not implement these during Phase 3 unless explicitly requested.

## Development Rules

1. Inspect existing code before modifying it.
2. Do not rewrite working functionality unnecessarily.
3. Do not delete existing authentication data.
4. Do not use destructive database resets.
5. Create migrations for database changes.
6. Test changes before committing.
7. Keep phases separate.
8. Explain architectural decisions.
9. Never assume the existing schema — inspect it first.
10. Maintain compatibility with the existing project structure.