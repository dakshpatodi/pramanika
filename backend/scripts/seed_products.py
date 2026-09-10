"""
Development seed script for the product catalogue.

Not imported by the running app anywhere - this is a standalone script,
kept separate from application logic per the brief's explicit instruction.

Run from backend/, with the venv active:
    python -m scripts.seed_products

(Must be run with `-m`, not `python scripts/seed_products.py` directly -
same reason Alembic needs `prepend_sys_path`: running as `-m` puts the
current directory, backend/, on sys.path so `app` is importable. Running
the file path directly would raise ModuleNotFoundError: No module named 'app'.)

Idempotent: every category/product is checked by slug before inserting,
so re-running this script never creates duplicates or errors.
"""

from app.database.session import SessionLocal
from app.models import Category, Inventory, Product, WeightUnit

CATEGORIES = [
    {"name": "Cereals", "slug": "cereals", "description": "Whole-grain breakfast cereals."},
    {"name": "Ready Mixes", "slug": "ready-mixes", "description": "Instant breakfast and snack mixes."},
    {"name": "Dry Fruits", "slug": "dry-fruits", "description": "Premium dried fruits and nuts."},
    {"name": "Snacks", "slug": "snacks", "description": "Wholesome, ready-to-eat snacks."},
    {"name": "Health Foods", "slug": "health-foods", "description": "Millets and other health-focused staples."},
]

# `quantity` drives each product's Inventory row (0 = deliberately seeded
# out of stock, small numbers = deliberately seeded low-stock) - the mix
# below is chosen so Phase 4's in_stock/low_stock logic has real cases
# of all three states to smoke-test against, not just "everything's fine".
PRODUCTS = [
    {
        "category_slug": "cereals",
        "name": "Multigrain Cereal",
        "slug": "multigrain-cereal",
        "sku": "PRM-CER-001",
        "short_description": "A wholesome blend of five grains.",
        "description": "A hearty multigrain cereal combining wheat, oats, barley, corn, and rice for a filling breakfast.",
        "price": 249.00,
        "compare_at_price": 299.00,
        "weight": 500,
        "weight_unit": WeightUnit.GRAM,
        "quantity": 40,
    },
    {
        "category_slug": "ready-mixes",
        "name": "Poha Ready Mix",
        "slug": "poha-ready-mix",
        "sku": "PRM-RMX-001",
        "short_description": "Flattened rice mix, ready in 10 minutes.",
        "description": "Pre-mixed flattened rice with spices - just add vegetables and cook.",
        "price": 189.00,
        "compare_at_price": None,
        "weight": 400,
        "weight_unit": WeightUnit.GRAM,
        "quantity": 55,
    },
    {
        "category_slug": "ready-mixes",
        "name": "Ragi Dosa Mix",
        "slug": "ragi-dosa-mix",
        "sku": "PRM-RMX-002",
        "short_description": "Finger millet dosa batter mix.",
        "description": "A traditional ragi (finger millet) dosa batter mix, ready with just water.",
        "price": 175.00,
        "compare_at_price": 199.00,
        "weight": 500,
        "weight_unit": WeightUnit.GRAM,
        "quantity": 8,  # deliberately low - tests the low_stock flag
    },
    {
        "category_slug": "dry-fruits",
        "name": "Premium Almonds",
        "slug": "premium-almonds",
        "sku": "PRM-DFR-001",
        "short_description": "California almonds, hand-selected.",
        "description": "Hand-selected California almonds, rich in vitamin E and healthy fats.",
        "price": 599.00,
        "compare_at_price": 699.00,
        "weight": 250,
        "weight_unit": WeightUnit.GRAM,
        "quantity": 25,
    },
    {
        "category_slug": "dry-fruits",
        "name": "Golden Raisins",
        "slug": "golden-raisins",
        "sku": "PRM-DFR-002",
        "short_description": "Seedless golden raisins.",
        "description": "Naturally sweet, seedless golden raisins - great for snacking or baking.",
        "price": 149.00,
        "compare_at_price": None,
        "weight": 250,
        "weight_unit": WeightUnit.GRAM,
        "quantity": 0,  # deliberately zero - tests the out-of-stock flag
    },
    {
        "category_slug": "health-foods",
        "name": "Millet Breakfast Mix",
        "slug": "millet-breakfast-mix",
        "sku": "PRM-HLF-001",
        "short_description": "A blend of five ancient millets.",
        "description": "A nutrient-dense blend of five ancient millets, perfect for a wholesome breakfast porridge.",
        "price": 279.00,
        "compare_at_price": 329.00,
        "weight": 500,
        "weight_unit": WeightUnit.GRAM,
        "quantity": 15,
    },
    {
        "category_slug": "snacks",
        "name": "Roasted Makhana",
        "slug": "roasted-makhana",
        "sku": "PRM-SNK-001",
        "short_description": "Lightly roasted fox nuts, lightly salted.",
        "description": "Crunchy, lightly roasted fox nuts (makhana) with a touch of sea salt - a guilt-free snack.",
        "price": 179.00,
        "compare_at_price": None,
        "weight": 100,
        "weight_unit": WeightUnit.GRAM,
        "quantity": 60,
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        categories_by_slug = {}
        for cat_data in CATEGORIES:
            existing = db.query(Category).filter(Category.slug == cat_data["slug"]).first()
            if existing:
                categories_by_slug[cat_data["slug"]] = existing
                print(f"Category '{cat_data['slug']}' already exists, skipping.")
                continue
            category = Category(**cat_data)
            db.add(category)
            db.flush()  # assigns category.id without committing yet
            categories_by_slug[cat_data["slug"]] = category
            print(f"Created category '{cat_data['slug']}'.")

        for prod_data in PRODUCTS:
            existing = db.query(Product).filter(Product.slug == prod_data["slug"]).first()
            if existing:
                print(f"Product '{prod_data['slug']}' already exists, skipping.")
                continue

            category = categories_by_slug[prod_data["category_slug"]]

            product = Product(
                category_id=category.id,
                name=prod_data["name"],
                slug=prod_data["slug"],
                sku=prod_data["sku"],
                short_description=prod_data["short_description"],
                description=prod_data["description"],
                price=prod_data["price"],
                compare_at_price=prod_data.get("compare_at_price"),
                weight=prod_data["weight"],
                weight_unit=prod_data["weight_unit"],
            )
            db.add(product)
            db.flush()  # assigns product.id for the Inventory FK below

            inventory = Inventory(
                product_id=product.id,
                quantity=prod_data["quantity"],
                low_stock_threshold=10,
            )
            db.add(inventory)
            print(f"Created product '{prod_data['slug']}' (qty={prod_data['quantity']}).")

        db.commit()
        print("\nSeed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()