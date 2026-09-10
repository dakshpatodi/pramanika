"""
Category business logic - read-only browsing for Phase 4 (no admin
category management yet).
"""

from typing import List

from sqlalchemy.orm import Session

from app.core.exceptions import CategoryNotFoundError
from app.repositories.category_repository import CategoryRepository
from app.schemas.category import CategoryListItem, CategoryResponse


class CategoryService:
    def __init__(self, db: Session):
        self.repository = CategoryRepository(db)

    def list_categories(self) -> List[CategoryListItem]:
        pairs = self.repository.list_active_with_product_counts()
        return [
            CategoryListItem(
                id=category.id,
                name=category.name,
                slug=category.slug,
                description=category.description,
                image_url=category.image_url,
                product_count=count,
            )
            for category, count in pairs
        ]

    def get_category(self, slug: str) -> CategoryResponse:
        category = self.repository.get_by_slug(slug)
        if category is None:
            raise CategoryNotFoundError(slug)
        return CategoryResponse.model_validate(category)