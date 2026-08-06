"""
Repositories package.

Each repository is the single place in the codebase that writes
SQLAlchemy queries for one model. Services depend on a repository's
method signatures, never on SQLAlchemy directly - this is the
Dependency Inversion half of the Repository Pattern: swapping the ORM,
adding caching, or changing a query's implementation only ever touches
one file here, never the service or route layers that call it.
"""