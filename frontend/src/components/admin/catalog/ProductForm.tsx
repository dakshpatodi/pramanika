"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";

import { FormField } from "@/components/admin/catalog/FormField";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { getApiErrorMessage } from "@/lib/errors";
import {
  EMPTY_PRODUCT,
  PRODUCT_FIELD_ORDER,
  isWeightUnit,
  productChanges,
  productCreateInput,
  productToValues,
  serverFieldErrors,
  validateProduct,
  type FormErrors,
  type ProductField,
  type ProductFormValues,
} from "@/lib/admin-catalog-form";
import { createAdminProduct, listAdminCategories, updateAdminProduct } from "@/services/admin-catalog";
import { WEIGHT_UNITS, type AdminProductDetail } from "@/types/admin-catalog";

type Status = { kind: "idle" } | { kind: "saved" } | { kind: "error"; message: string };
type Control = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

interface ProductFormProps {
  /** Present: edit this product. Absent: create a new one. */
  product?: AdminProductDetail;
  /** Edit mode: called with the server's copy after a save. */
  onSaved?: (product: AdminProductDetail) => void;
}

const FIELD_NAMES = PRODUCT_FIELD_ORDER as readonly ProductField[];

/**
 * Create or edit a product. Creating also sets the opening stock; editing never touches stock or
 * active state (stock lives under Inventory, activation has its own confirmed button) and sends only
 * the fields that changed. Money goes to the server as text, never as a float. The server re-checks
 * everything: its field complaints are shown on the inputs and what you typed is kept.
 */
export function ProductForm({ product, onSaved }: ProductFormProps) {
  const editing = product !== undefined;
  const categories = useAdminQuery(
    "product-form-categories",
    () => listAdminCategories({ is_active: true, page_size: 100, sort: "name", order: "asc" }),
    { failure: "We couldn't load the categories." }
  );

  const [saved, setSaved] = useState<AdminProductDetail | null>(product ?? null);
  const [values, setValues] = useState<ProductFormValues>(() => (product ? productToValues(product) : EMPTY_PRODUCT));
  const [errors, setErrors] = useState<FormErrors<ProductField>>({});
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [created, setCreated] = useState<AdminProductDetail | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const refs = useRef<Partial<Record<ProductField, Control | null>>>({});
  const focusAfterSave = useRef<ProductField | null>(null);

  // Inputs are disabled while saving, so a field the server refused is focused once saving ends.
  useEffect(() => {
    if (!saving && focusAfterSave.current) {
      refs.current[focusAfterSave.current]?.focus();
      focusAfterSave.current = null;
    }
  }, [saving]);

  const dirty = saved ? Object.keys(productChanges(saved, values)).length > 0 : true;

  // The category choices: active categories, plus this product's own category even if it is hidden.
  const options = [...(categories.data?.categories ?? []).map((c) => ({ id: c.id, label: c.name }))];
  if (product && !options.some((o) => o.id === product.category.id)) {
    options.unshift({ id: product.category.id, label: `${product.category.name}${product.category.is_active ? "" : " (inactive)"}` });
  }

  function edit<K extends keyof ProductFormValues>(field: K, value: ProductFormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }));
    if (field in errors) setErrors((current) => ({ ...current, [field]: undefined }));
    setStatus((current) => (current.kind === "idle" ? current : { kind: "idle" }));
  }

  function focusFirst(found: FormErrors<ProductField>) {
    const first = PRODUCT_FIELD_ORDER.find((field) => found[field]);
    if (first) refs.current[first]?.focus();
    return Boolean(first);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingRef.current) return;

    const found = validateProduct(values, editing ? "edit" : "create");
    setErrors(found);
    if (focusFirst(found)) return;

    savingRef.current = true;
    setSaving(true);
    setStatus({ kind: "idle" });
    try {
      if (saved) {
        const changes = productChanges(saved, values);
        if (Object.keys(changes).length === 0) return;
        const updated = await updateAdminProduct(saved.id, changes);
        setSaved(updated);
        setValues(productToValues(updated));
        setStatus({ kind: "saved" });
        onSaved?.(updated);
      } else {
        setCreated(await createAdminProduct(productCreateInput(values)));
      }
    } catch (failure) {
      const fieldErrors = serverFieldErrors(failure, FIELD_NAMES);
      setErrors(fieldErrors);
      focusAfterSave.current = PRODUCT_FIELD_ORDER.find((field) => fieldErrors[field]) ?? null;
      setStatus({ kind: "error", message: getApiErrorMessage(failure, "We couldn't save the product. Please try again.") });
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  if (created) {
    return (
      <div role="status" className="flex flex-col items-start gap-4 rounded-2xl border border-border bg-card p-6 shadow-card">
        <p className="flex items-center gap-2 font-medium text-foreground">
          <Check className="h-4 w-4 text-primary" aria-hidden="true" />
          Product &quot;{created.name}&quot; created ({created.sku}).
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="primary" size="sm">
            <Link href={`/admin/products/${created.id}`}>Open it</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/admin/products">Back to products</Link>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setCreated(null);
              setValues(EMPTY_PRODUCT);
              setErrors({});
              setStatus({ kind: "idle" });
            }}
          >
            Add another
          </Button>
        </div>
      </div>
    );
  }

  const ref = (field: ProductField) => (element: Control | null) => {
    refs.current[field] = element;
  };
  const text = (field: ProductField, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <Input
      name={field}
      ref={ref(field)}
      value={values[field] as string}
      onChange={(e) => edit(field, e.target.value as never)}
      disabled={saving}
      {...extra}
    />
  );
  const area = (field: ProductField, max: number, rows = 4) => (
    <Textarea
      name={field}
      ref={ref(field)}
      rows={rows}
      value={values[field] as string}
      onChange={(e) => edit(field, e.target.value as never)}
      disabled={saving}
      maxLength={max}
    />
  );
  const fieldset = "flex flex-col gap-5 border-t border-border pt-5 first:border-t-0 first:pt-0";
  const legend = "font-display text-lg font-semibold text-foreground";

  return (
    <form onSubmit={submit} noValidate className="flex max-w-3xl flex-col gap-6 rounded-2xl border border-border bg-card p-6 shadow-card">
      {status.kind === "error" ? <Banner>{status.message}</Banner> : null}
      {status.kind === "saved" ? (
        <p role="status" className="flex items-center gap-2 text-sm font-medium text-primary">
          <Check className="h-4 w-4" aria-hidden="true" />
          Saved.
        </p>
      ) : null}
      {categories.error ? <Banner>{categories.error}</Banner> : null}

      <fieldset className={fieldset}>
        <legend className={legend}>Basics</legend>
        <FormField id="product-category" label="Category" required error={errors.category_id}>
          <Select
            name="category_id"
            ref={ref("category_id")}
            value={values.category_id}
            onChange={(e) => edit("category_id", e.target.value)}
            disabled={saving || (categories.loading && !categories.data && !editing)}
          >
            <option value="">{categories.loading && !categories.data ? "Loading categories..." : "Choose a category"}</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="product-name" label="Name" required error={errors.name}>
          {text("name", { maxLength: 200 })}
        </FormField>
        <div className="grid gap-5 sm:grid-cols-2">
          <FormField
            id="product-sku"
            label="SKU"
            required
            error={errors.sku}
            hint="Letters, digits, . _ - ; saved in capitals."
          >
            {text("sku", { maxLength: 50 })}
          </FormField>
          <FormField
            id="product-slug"
            label="Slug"
            required={editing}
            error={errors.slug}
            hint={editing ? "Part of the product's web address. Changing it changes the link." : "Leave empty to make one from the name."}
          >
            {text("slug", { maxLength: 220 })}
          </FormField>
        </div>
      </fieldset>

      <fieldset className={fieldset}>
        <legend className={legend}>Price</legend>
        <div className="grid gap-5 sm:grid-cols-2">
          <FormField id="product-price" label="Price (₹)" required error={errors.price}>
            {text("price", { inputMode: "decimal", placeholder: "249.00" })}
          </FormField>
          <FormField
            id="product-compare"
            label="Compare-at price (₹)"
            error={errors.compare_at_price}
            hint="The 'was' price shown struck through. Must be higher than the price."
          >
            {text("compare_at_price", { inputMode: "decimal" })}
          </FormField>
        </div>
      </fieldset>

      <fieldset className={fieldset}>
        <legend className={legend}>Details</legend>
        <FormField id="product-short" label="Short description" error={errors.short_description}>
          {area("short_description", 500, 2)}
        </FormField>
        <FormField id="product-description" label="Description" error={errors.description}>
          {area("description", 10000, 6)}
        </FormField>
        <FormField id="product-ingredients" label="Ingredients" error={errors.ingredients}>
          {area("ingredients", 5000, 3)}
        </FormField>
        <FormField id="product-nutrition" label="Nutritional information" error={errors.nutritional_information}>
          {area("nutritional_information", 5000, 3)}
        </FormField>
        <div className="grid gap-5 sm:grid-cols-2">
          <FormField id="product-weight" label="Weight / volume" error={errors.weight}>
            {text("weight", { inputMode: "decimal", placeholder: "500" })}
          </FormField>
          <FormField id="product-unit" label="Unit" error={errors.weight_unit}>
            <Select
              name="weight_unit"
              ref={ref("weight_unit")}
              value={values.weight_unit}
              onChange={(e) => edit("weight_unit", isWeightUnit(e.target.value) ? e.target.value : "")}
              disabled={saving}
            >
              <option value="">No unit</option>
              {WEIGHT_UNITS.map((unit) => (
                <option key={unit} value={unit}>
                  {unit}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
        <FormField id="product-image" label="Image address" error={errors.image_url} hint="An https:// address, or a path on this site such as /images/oats.jpg.">
          {text("image_url", { maxLength: 500 })}
        </FormField>
      </fieldset>

      {editing && product ? (
        <fieldset className={fieldset}>
          <legend className={legend}>Stock</legend>
          <p className="text-sm text-muted-foreground">
            {product.available_quantity.toLocaleString("en-IN")} available ({product.quantity.toLocaleString("en-IN")} in stock,{" "}
            {product.reserved_quantity.toLocaleString("en-IN")} reserved by open orders). Stock is managed under Inventory, not here.
          </p>
          <Link href={`/admin/inventory/${product.id}`} className="mt-2 inline-block text-sm font-medium text-primary hover:underline">
            Manage stock
          </Link>
        </fieldset>
      ) : (
        <fieldset className={fieldset}>
          <legend className={legend}>Opening stock</legend>
          <div className="grid gap-5 sm:grid-cols-2">
            <FormField id="product-quantity" label="Units in stock" error={errors.initial_quantity}>
              {text("initial_quantity", { inputMode: "numeric" })}
            </FormField>
            <FormField id="product-threshold" label="Low-stock warning at" error={errors.low_stock_threshold} hint="Flagged as low when this many or fewer are available.">
              {text("low_stock_threshold", { inputMode: "numeric" })}
            </FormField>
          </div>
          <label className="flex items-center gap-3 text-sm text-foreground">
            <Checkbox checked={values.is_active} onChange={(e) => edit("is_active", e.target.checked)} disabled={saving} />
            Show this product in the shop
          </label>
        </fieldset>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" disabled={saving || (editing && !dirty)}>
          {saving ? "Saving..." : editing ? "Save changes" : "Create product"}
        </Button>
        {editing && dirty ? (
          <Button
            type="button"
            variant="ghost"
            disabled={saving}
            onClick={() => {
              if (saved) setValues(productToValues(saved));
              setErrors({});
              setStatus({ kind: "idle" });
            }}
          >
            Discard changes
          </Button>
        ) : null}
        <Button asChild variant="ghost">
          <Link href="/admin/products">Back to products</Link>
        </Button>
      </div>
    </form>
  );
}
