/**
 * Form helpers for the admin category and product forms: light client-side checks (the SERVER stays
 * the authority and re-checks everything), and the exact request bodies - on edit only the fields
 * that changed. All values are strings while editing; money is sent as a string, never a float.
 */

import axios from "axios";

import type {
  AdminCategory,
  AdminProductDetail,
  CategoryCreateInput,
  CategoryUpdateInput,
  ProductCreateInput,
  ProductUpdateInput,
  WeightUnit,
} from "@/types/admin-catalog";
import { WEIGHT_UNITS } from "@/types/admin-catalog";

export type FormErrors<F extends string> = Partial<Record<F, string>>;

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SKU = /^[A-Z0-9][A-Z0-9._-]*$/;
const IMAGE = /^(https?:\/\/\S+|\/\S*)$/;
const MONEY = /^\d{1,8}(\.\d{1,2})?$/;
const WEIGHT = /^\d{1,7}(\.\d{1,3})?$/;
const WHOLE = /^\d+$/;

export const MAX_STOCK = 1_000_000;

const trimmed = (value: string) => value.trim();
const orNull = (value: string): string | null => trimmed(value) || null;

function imageError(value: string): string | undefined {
  const url = trimmed(value);
  if (!url) return undefined;
  if (url.length > 500) return "Use at most 500 characters.";
  if (url.startsWith("//") || !IMAGE.test(url)) return "Use an http(s) address, or a path starting with /.";
  return undefined;
}

function slugError(value: string, required: boolean, max: number): string | undefined {
  const slug = trimmed(value).toLowerCase();
  if (!slug) return required ? "Enter a slug." : undefined;
  if (slug.length > max) return `Use at most ${max} characters.`;
  if (!SLUG.test(slug)) return "Use lowercase letters, digits and single hyphens only (e.g. rolled-oats).";
  return undefined;
}

function textError(value: string, max: number): string | undefined {
  return trimmed(value).length > max ? `Use at most ${max} characters.` : undefined;
}

// ---------------------------------------------------------------- categories

export interface CategoryFormValues {
  name: string;
  slug: string;
  description: string;
  image_url: string;
  is_active: boolean;
}
export type CategoryField = "name" | "slug" | "description" | "image_url";
export const CATEGORY_FIELDS: CategoryField[] = ["name", "slug", "description", "image_url"];
export const CATEGORY_FIELD_ORDER = CATEGORY_FIELDS;

export const EMPTY_CATEGORY: CategoryFormValues = { name: "", slug: "", description: "", image_url: "", is_active: true };

export function categoryToValues(category: AdminCategory): CategoryFormValues {
  return {
    name: category.name,
    slug: category.slug,
    description: category.description ?? "",
    image_url: category.image_url ?? "",
    is_active: category.is_active,
  };
}

export function validateCategory(values: CategoryFormValues, mode: "create" | "edit"): FormErrors<CategoryField> {
  const errors: FormErrors<CategoryField> = {};
  const name = trimmed(values.name);
  if (!name) errors.name = "Enter a name.";
  else if (name.length > 100) errors.name = "Use at most 100 characters.";
  const slug = slugError(values.slug, mode === "edit", 120);
  if (slug) errors.slug = slug;
  const description = textError(values.description, 2000);
  if (description) errors.description = description;
  const image = imageError(values.image_url);
  if (image) errors.image_url = image;
  return errors;
}

export function categoryCreateInput(values: CategoryFormValues): CategoryCreateInput {
  const input: CategoryCreateInput = { name: trimmed(values.name), is_active: values.is_active };
  const slug = trimmed(values.slug).toLowerCase();
  if (slug) input.slug = slug;
  const description = orNull(values.description);
  if (description) input.description = description;
  const image = orNull(values.image_url);
  if (image) input.image_url = image;
  return input;
}

/** Only what differs from the saved category; a cleared optional field is sent as null. */
export function categoryChanges(category: AdminCategory, values: CategoryFormValues): CategoryUpdateInput {
  const changes: CategoryUpdateInput = {};
  if (trimmed(values.name) !== category.name) changes.name = trimmed(values.name);
  const slug = trimmed(values.slug).toLowerCase();
  if (slug !== category.slug) changes.slug = slug;
  if (orNull(values.description) !== category.description) changes.description = orNull(values.description);
  if (orNull(values.image_url) !== category.image_url) changes.image_url = orNull(values.image_url);
  return changes;
}

// ------------------------------------------------------------------ products

export interface ProductFormValues {
  category_id: string;
  name: string;
  slug: string;
  sku: string;
  price: string;
  compare_at_price: string;
  short_description: string;
  description: string;
  weight: string;
  weight_unit: WeightUnit | "";
  ingredients: string;
  nutritional_information: string;
  image_url: string;
  is_active: boolean;
  initial_quantity: string;
  low_stock_threshold: string;
}
export type ProductField = keyof ProductFormValues;

export const EMPTY_PRODUCT: ProductFormValues = {
  category_id: "",
  name: "",
  slug: "",
  sku: "",
  price: "",
  compare_at_price: "",
  short_description: "",
  description: "",
  weight: "",
  weight_unit: "",
  ingredients: "",
  nutritional_information: "",
  image_url: "",
  is_active: true,
  initial_quantity: "0",
  low_stock_threshold: "10",
};

/** The order fields appear on the page: the first invalid one gets focus. */
export const PRODUCT_FIELD_ORDER: ProductField[] = [
  "category_id", "name", "slug", "sku", "price", "compare_at_price", "short_description", "description",
  "ingredients", "nutritional_information", "weight", "weight_unit", "image_url", "initial_quantity", "low_stock_threshold",
];

const money = (n: number) => n.toFixed(2);

export function productToValues(product: AdminProductDetail): ProductFormValues {
  return {
    category_id: product.category.id,
    name: product.name,
    slug: product.slug,
    sku: product.sku,
    price: money(product.price),
    compare_at_price: product.compare_at_price === null ? "" : money(product.compare_at_price),
    short_description: product.short_description ?? "",
    description: product.description ?? "",
    weight: product.weight === null ? "" : String(product.weight),
    weight_unit: product.weight_unit ?? "",
    ingredients: product.ingredients ?? "",
    nutritional_information: product.nutritional_information ?? "",
    image_url: product.image_url ?? "",
    is_active: product.is_active,
    initial_quantity: "0",
    low_stock_threshold: "10",
  };
}

export function validateProduct(values: ProductFormValues, mode: "create" | "edit"): FormErrors<ProductField> {
  const errors: FormErrors<ProductField> = {};
  if (!values.category_id) errors.category_id = "Choose a category.";

  const name = trimmed(values.name);
  if (!name) errors.name = "Enter a name.";
  else if (name.length > 200) errors.name = "Use at most 200 characters.";

  const slug = slugError(values.slug, mode === "edit", 220);
  if (slug) errors.slug = slug;

  const sku = trimmed(values.sku).toUpperCase();
  if (!sku) errors.sku = "Enter a SKU.";
  else if (sku.length > 50) errors.sku = "Use at most 50 characters.";
  else if (!SKU.test(sku)) errors.sku = "Use letters, digits, '.', '_' and '-' only, starting with a letter or digit.";

  const price = trimmed(values.price);
  let priceValue: number | null = null;
  if (!price) errors.price = "Enter a price.";
  else if (!MONEY.test(price)) errors.price = "Enter an amount like 249 or 249.50 (at most 2 decimals).";
  else if (Number(price) <= 0) errors.price = "The price must be more than 0.";
  else priceValue = Number(price);

  const compare = trimmed(values.compare_at_price);
  if (compare) {
    if (!MONEY.test(compare)) errors.compare_at_price = "Enter an amount like 299 or 299.50 (at most 2 decimals).";
    else if (Number(compare) <= 0) errors.compare_at_price = "Must be more than 0, or leave it empty.";
    else if (priceValue !== null && Number(compare) <= priceValue) errors.compare_at_price = "Must be higher than the price, or leave it empty.";
  }

  const short = textError(values.short_description, 500);
  if (short) errors.short_description = short;
  const description = textError(values.description, 10000);
  if (description) errors.description = description;
  const ingredients = textError(values.ingredients, 5000);
  if (ingredients) errors.ingredients = ingredients;
  const nutrition = textError(values.nutritional_information, 5000);
  if (nutrition) errors.nutritional_information = nutrition;

  const weight = trimmed(values.weight);
  if (weight) {
    if (!WEIGHT.test(weight)) errors.weight = "Enter an amount like 500 or 0.5 (at most 3 decimals).";
    else if (Number(weight) <= 0) errors.weight = "Must be more than 0, or leave it empty.";
    if (!values.weight_unit) errors.weight_unit = "Choose a unit for the weight.";
  } else if (values.weight_unit) {
    errors.weight = "Enter the weight, or clear the unit.";
  }

  const image = imageError(values.image_url);
  if (image) errors.image_url = image;

  if (mode === "create") {
    for (const field of ["initial_quantity", "low_stock_threshold"] as const) {
      const raw = trimmed(values[field]);
      if (!WHOLE.test(raw)) errors[field] = "Enter a whole number, 0 or more.";
      else if (Number(raw) > MAX_STOCK) errors[field] = `Use at most ${MAX_STOCK.toLocaleString("en-IN")}.`;
    }
  }
  return errors;
}

export function productCreateInput(values: ProductFormValues): ProductCreateInput {
  const input: ProductCreateInput = {
    category_id: values.category_id,
    name: trimmed(values.name),
    sku: trimmed(values.sku).toUpperCase(),
    price: trimmed(values.price),
    is_active: values.is_active,
    initial_quantity: Number(trimmed(values.initial_quantity)),
    low_stock_threshold: Number(trimmed(values.low_stock_threshold)),
  };
  const slug = trimmed(values.slug).toLowerCase();
  if (slug) input.slug = slug;
  if (trimmed(values.compare_at_price)) input.compare_at_price = trimmed(values.compare_at_price);
  for (const field of ["short_description", "description", "ingredients", "nutritional_information", "image_url"] as const) {
    const value = orNull(values[field]);
    if (value) input[field] = value;
  }
  if (trimmed(values.weight) && values.weight_unit) {
    input.weight = trimmed(values.weight);
    input.weight_unit = values.weight_unit;
  }
  return input;
}

const sameNumber = (text: string, current: number | null): boolean => {
  const value = trimmed(text);
  if (!value) return current === null;
  return current !== null && Number(value) === current;
};

/** Only what differs from the saved product. Stock and active state are never in here. */
export function productChanges(product: AdminProductDetail, values: ProductFormValues): ProductUpdateInput {
  const changes: ProductUpdateInput = {};
  if (values.category_id !== product.category.id) changes.category_id = values.category_id;
  if (trimmed(values.name) !== product.name) changes.name = trimmed(values.name);
  const slug = trimmed(values.slug).toLowerCase();
  if (slug !== product.slug) changes.slug = slug;
  const sku = trimmed(values.sku).toUpperCase();
  if (sku !== product.sku) changes.sku = sku;
  if (!sameNumber(values.price, product.price)) changes.price = trimmed(values.price);
  if (!sameNumber(values.compare_at_price, product.compare_at_price)) {
    changes.compare_at_price = orNull(values.compare_at_price);
  }
  for (const field of ["short_description", "description", "ingredients", "nutritional_information", "image_url"] as const) {
    if (orNull(values[field]) !== product[field]) changes[field] = orNull(values[field]);
  }
  const unit = values.weight_unit || null;
  if (!sameNumber(values.weight, product.weight) || unit !== product.weight_unit) {
    changes.weight = orNull(values.weight);          // the server wants weight and unit together
    changes.weight_unit = unit;
  }
  return changes;
}

export function isWeightUnit(value: string): value is WeightUnit {
  return (WEIGHT_UNITS as string[]).includes(value);
}

// ------------------------------------------------------------- server errors

/**
 * Field-level problems from a failed save, so the input can be marked: from the 422 `errors` list, or
 * from a message shaped `field: reason`. Unknown fields are left out (the banner shows the message).
 */
export function serverFieldErrors<F extends string>(error: unknown, known: readonly F[]): FormErrors<F> {
  const out: FormErrors<F> = {};
  if (!axios.isAxiosError(error)) return out;
  const body = error.response?.data as { message?: string; errors?: Array<{ loc?: unknown[]; msg?: string }> } | undefined;
  const clean = (text: string) => text.replace(/^Value error, /, "");

  for (const item of body?.errors ?? []) {
    const field = item.loc?.[item.loc.length - 1];
    if (typeof field === "string" && (known as readonly string[]).includes(field) && item.msg && !out[field as F]) {
      out[field as F] = clean(item.msg);
    }
  }
  const match = /^([a-z_]+): ([\s\S]+)$/.exec(body?.message ?? "");
  if (match && (known as readonly string[]).includes(match[1]) && !out[match[1] as F]) {
    out[match[1] as F] = clean(match[2]);
  }
  return out;
}
