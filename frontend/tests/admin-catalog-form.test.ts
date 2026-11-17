import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";

import {
  EMPTY_CATEGORY,
  EMPTY_PRODUCT,
  categoryChanges,
  categoryCreateInput,
  productChanges,
  productCreateInput,
  productToValues,
  serverFieldErrors,
  validateCategory,
  validateProduct,
  type ProductFormValues,
} from "@/lib/admin-catalog-form";
import { category, productDetail } from "./admin-fixtures";

const okProduct = (over: Partial<ProductFormValues> = {}): ProductFormValues => ({
  ...EMPTY_PRODUCT, category_id: "c1", name: "Muesli", sku: "MUE-001", price: "249", ...over,
});

describe("validateCategory", () => {
  it("accepts a minimal category and treats the slug as optional on create", () => {
    expect(validateCategory({ ...EMPTY_CATEGORY, name: "Cereals" }, "create")).toEqual({});
  });
  it("needs a name; needs a slug only when editing", () => {
    expect(validateCategory(EMPTY_CATEGORY, "create").name).toBe("Enter a name.");
    expect(validateCategory({ ...EMPTY_CATEGORY, name: "A" }, "edit").slug).toBe("Enter a slug.");
  });
  it.each(["Bad Slug", "double--hyphen", "-lead", "trail-", "under_score", "ünï"])("rejects slug %s", (slug) => {
    expect(validateCategory({ ...EMPTY_CATEGORY, name: "A", slug }, "create").slug).toMatch(/lowercase letters/);
  });
  it("lower-cases the slug before checking, like the server", () => {
    expect(validateCategory({ ...EMPTY_CATEGORY, name: "A", slug: "  Rolled-Oats " }, "create")).toEqual({});
  });
  it("enforces the length limits", () => {
    const v = { ...EMPTY_CATEGORY, name: "n".repeat(101), description: "d".repeat(2001), slug: "s".repeat(121) };
    const e = validateCategory(v, "create");
    expect([e.name, e.description, e.slug].every((m) => /at most/.test(m ?? ""))).toBe(true);
  });
  it.each(["//evil.com/x.png", "javascript:alert(1)", "ftp://x.com/a.png", "data:image/png;base64,AAA", "not a url"])(
    "rejects image address %s",
    (image_url) => expect(validateCategory({ ...EMPTY_CATEGORY, name: "A", image_url }, "create").image_url).toBeTruthy()
  );
  it.each(["https://cdn.example.com/a.png", "http://x.com/a", "/images/oats.jpg"])("accepts image address %s", (image_url) =>
    expect(validateCategory({ ...EMPTY_CATEGORY, name: "A", image_url }, "create").image_url).toBeUndefined()
  );
});

describe("category request bodies", () => {
  it("create trims, lower-cases the slug and leaves out blanks", () => {
    expect(categoryCreateInput({ ...EMPTY_CATEGORY, name: "  Cereals ", slug: " Whole-Grain ", is_active: false })).toEqual({
      name: "Cereals", slug: "whole-grain", is_active: false,
    });
    expect(categoryCreateInput({ ...EMPTY_CATEGORY, name: "A", description: " hi ", image_url: "/a.png" })).toEqual({
      name: "A", description: "hi", image_url: "/a.png", is_active: true,
    });
  });
  it("edit sends nothing when nothing changed (even with stray spaces or capitals)", () => {
    const c = category({ description: null });
    expect(categoryChanges(c, { name: " Cereals ", slug: "CEREALS", description: "  ", image_url: "", is_active: true })).toEqual({});
  });
  it("edit sends only what changed, and null for a cleared optional field", () => {
    const c = category({ description: "Old", image_url: "/a.png" });
    expect(categoryChanges(c, { name: "Grains", slug: "cereals", description: "", image_url: "/a.png", is_active: true })).toEqual({
      name: "Grains", description: null,
    });
  });
});

describe("validateProduct", () => {
  it("accepts the minimum and a fully filled product", () => {
    expect(validateProduct(okProduct(), "create")).toEqual({});
    expect(
      validateProduct(
        okProduct({ slug: "muesli", compare_at_price: "299.50", weight: "0.5", weight_unit: "kg", image_url: "/m.png", initial_quantity: "20" }),
        "create"
      )
    ).toEqual({});
  });
  it("requires category, name, sku and price", () => {
    const e = validateProduct(EMPTY_PRODUCT, "create");
    expect(Object.keys(e).sort()).toEqual(["category_id", "name", "price", "sku"]);
  });
  it.each(["abc", "12.345", "1e3", "-5", "0", "0.00", "1,000", " "])("rejects price %j", (price) => {
    expect(validateProduct(okProduct({ price }), "create").price).toBeTruthy();
  });
  it.each(["249", "249.5", "249.50", " 12 ", "0.01"])("accepts price %j", (price) => {
    expect(validateProduct(okProduct({ price }), "create").price).toBeUndefined();
  });
  it("compare-at must beat the price", () => {
    expect(validateProduct(okProduct({ compare_at_price: "249" }), "create").compare_at_price).toMatch(/higher than the price/);
    expect(validateProduct(okProduct({ compare_at_price: "200" }), "create").compare_at_price).toMatch(/higher than the price/);
    expect(validateProduct(okProduct({ compare_at_price: "250" }), "create").compare_at_price).toBeUndefined();
  });
  it("accepts a lower-case SKU (stored upper-case) and rejects odd characters", () => {
    expect(validateProduct(okProduct({ sku: "mue-001" }), "create").sku).toBeUndefined();
    for (const sku of ["has space", "-lead", "a/b", "é1"]) expect(validateProduct(okProduct({ sku }), "create").sku).toBeTruthy();
  });
  it("weight and unit go together", () => {
    expect(validateProduct(okProduct({ weight: "500" }), "create").weight_unit).toBe("Choose a unit for the weight.");
    expect(validateProduct(okProduct({ weight_unit: "g" }), "create").weight).toBe("Enter the weight, or clear the unit.");
    expect(validateProduct(okProduct({ weight: "0", weight_unit: "g" }), "create").weight).toBeTruthy();
    expect(validateProduct(okProduct({ weight: "1.2345", weight_unit: "g" }), "create").weight).toBeTruthy();
  });
  it("opening stock must be whole numbers within the limit - on create only", () => {
    for (const bad of ["", "-1", "1.5", "abc", "1000001"]) {
      expect(validateProduct(okProduct({ initial_quantity: bad }), "create").initial_quantity).toBeTruthy();
      expect(validateProduct(okProduct({ low_stock_threshold: bad }), "create").low_stock_threshold).toBeTruthy();
    }
    expect(validateProduct(okProduct({ initial_quantity: "1000000" }), "create").initial_quantity).toBeUndefined();
    expect(validateProduct(okProduct({ initial_quantity: "junk" }), "edit").initial_quantity).toBeUndefined();
  });
  it("needs a slug when editing", () => {
    expect(validateProduct(okProduct(), "edit").slug).toBe("Enter a slug.");
  });
  it("enforces text limits", () => {
    const e = validateProduct(
      okProduct({ short_description: "x".repeat(501), description: "x".repeat(10001), ingredients: "x".repeat(5001), nutritional_information: "x".repeat(5001), name: "n".repeat(201) }),
      "create"
    );
    expect(Object.keys(e).sort()).toEqual(["description", "ingredients", "name", "nutritional_information", "short_description"]);
  });
});

describe("product request bodies", () => {
  it("create: money stays text, SKU upper-case, stock numeric, blanks omitted", () => {
    expect(productCreateInput(okProduct({ sku: " mue-001 ", price: " 249.50 ", initial_quantity: "20", low_stock_threshold: "5" }))).toEqual({
      category_id: "c1", name: "Muesli", sku: "MUE-001", price: "249.50", is_active: true, initial_quantity: 20, low_stock_threshold: 5,
    });
  });
  it("create: includes optional fields only when filled, and weight with its unit", () => {
    expect(productCreateInput(okProduct({ weight: "500", weight_unit: "" }))).not.toHaveProperty("weight");
    const body = productCreateInput(okProduct({ slug: "Muesli", compare_at_price: "299", short_description: " Crunchy ", weight: "500", weight_unit: "g", image_url: "/m.png" }));
    expect(body).toMatchObject({ slug: "muesli", compare_at_price: "299", short_description: "Crunchy", weight: "500", weight_unit: "g", image_url: "/m.png" });
    expect("description" in body).toBe(false);
  });
  const saved = productDetail();
  const same = (): ProductFormValues => productToValues(saved);
  it("edit: an untouched form changes nothing - 249.00 is the same as 249", () => {
    expect(productChanges(saved, same())).toEqual({});
    expect(productChanges(saved, { ...same(), price: "249" })).toEqual({});
    expect(productChanges(saved, { ...same(), sku: "mue-001", slug: "MUESLI", name: " Muesli " })).toEqual({});
  });
  it("edit: sends only the changed fields, money as text", () => {
    expect(productChanges(saved, { ...same(), price: "259.50", name: "Muesli Deluxe" })).toEqual({ price: "259.50", name: "Muesli Deluxe" });
  });
  it("edit: clearing an optional field sends null", () => {
    expect(productChanges(saved, { ...same(), compare_at_price: "", description: "", image_url: "" })).toEqual({
      compare_at_price: null, description: null,
    });
  });
  it("edit: a weight or unit change sends both together; clearing both sends nulls", () => {
    expect(productChanges(saved, { ...same(), weight: "750" })).toEqual({ weight: "750", weight_unit: "g" });
    expect(productChanges(saved, { ...same(), weight_unit: "kg" })).toEqual({ weight: "500", weight_unit: "kg" });
    expect(productChanges(saved, { ...same(), weight: "", weight_unit: "" })).toEqual({ weight: null, weight_unit: null });
  });
  it("edit: moving category is sent; stock and active state never are", () => {
    const changes = productChanges(saved, { ...same(), category_id: "c2", is_active: false, initial_quantity: "999", low_stock_threshold: "1" });
    expect(changes).toEqual({ category_id: "c2" });
  });
  it("productToValues shows money with two decimals and blanks for nulls", () => {
    const v = productToValues(productDetail({ compare_at_price: null, weight: null, weight_unit: null, description: null }));
    expect(v).toMatchObject({ price: "249.00", compare_at_price: "", weight: "", weight_unit: "", description: "" });
  });
});

describe("serverFieldErrors", () => {
  const failure = (data: unknown) =>
    new AxiosError("x", "ERR", undefined, undefined, { status: 422, data, statusText: "", headers: {}, config: {} as never });
  const known = ["name", "price", "sku"] as const;
  it("reads the 422 errors list (last location part, 'Value error' prefix removed)", () => {
    const e = failure({ message: "price: x", errors: [{ loc: ["body", "price"], msg: "Value error, Must be more than 0." }, { loc: ["body", "nope"], msg: "ignored" }] });
    expect(serverFieldErrors(e, known)).toEqual({ price: "Must be more than 0." });
  });
  it("reads a 'field: reason' message from a business rule", () => {
    expect(serverFieldErrors(failure({ message: "sku: that value is already in use." }), known)).toEqual({ sku: "that value is already in use." });
  });
  it("ignores unknown fields, plain messages and non-HTTP errors", () => {
    expect(serverFieldErrors(failure({ message: "category_id: not found" }), known)).toEqual({});
    expect(serverFieldErrors(failure({ message: "Something else" }), known)).toEqual({});
    expect(serverFieldErrors(new Error("boom"), known)).toEqual({});
  });
});
