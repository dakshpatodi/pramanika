"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";

import { FormField } from "@/components/admin/catalog/FormField";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { getApiErrorMessage } from "@/lib/errors";
import {
  CATEGORY_FIELDS,
  CATEGORY_FIELD_ORDER,
  EMPTY_CATEGORY,
  categoryChanges,
  categoryCreateInput,
  categoryToValues,
  serverFieldErrors,
  validateCategory,
  type CategoryField,
  type CategoryFormValues,
  type FormErrors,
} from "@/lib/admin-catalog-form";
import { createAdminCategory, updateAdminCategory } from "@/services/admin-catalog";
import type { AdminCategory } from "@/types/admin-catalog";

type Status = { kind: "idle" } | { kind: "saved" } | { kind: "error"; message: string };

interface CategoryFormProps {
  /** Present: edit this category. Absent: create a new one. */
  category?: AdminCategory;
  /** Edit mode: called with the server's copy after a save. */
  onSaved?: (category: AdminCategory) => void;
}

/**
 * Create or edit a category. Edit sends only the fields that changed (a cleared description or image
 * goes as null). The server re-checks everything: its field complaints are shown on the inputs, and
 * what you typed is kept. Active state is not on the edit form (it has its own confirmed button).
 */
export function CategoryForm({ category, onSaved }: CategoryFormProps) {
  const editing = category !== undefined;
  const [saved, setSaved] = useState<AdminCategory | null>(category ?? null);
  const [values, setValues] = useState<CategoryFormValues>(() => (category ? categoryToValues(category) : EMPTY_CATEGORY));
  const [errors, setErrors] = useState<FormErrors<CategoryField>>({});
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [created, setCreated] = useState<AdminCategory | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const refs = useRef<Partial<Record<CategoryField, HTMLInputElement | HTMLTextAreaElement | null>>>({});
  const focusAfterSave = useRef<CategoryField | null>(null);

  // Inputs are disabled while saving, so a field the server refused is focused once saving ends.
  useEffect(() => {
    if (!saving && focusAfterSave.current) {
      refs.current[focusAfterSave.current]?.focus();
      focusAfterSave.current = null;
    }
  }, [saving]);

  const dirty = saved ? Object.keys(categoryChanges(saved, values)).length > 0 : true;

  function edit<K extends keyof CategoryFormValues>(field: K, value: CategoryFormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }));
    if (field in errors) setErrors((current) => ({ ...current, [field]: undefined }));
    setStatus((current) => (current.kind === "idle" ? current : { kind: "idle" }));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingRef.current) return;

    const found = validateCategory(values, editing ? "edit" : "create");
    setErrors(found);
    const firstInvalid = CATEGORY_FIELD_ORDER.find((field) => found[field]);
    if (firstInvalid) {
      refs.current[firstInvalid]?.focus();
      return;
    }

    savingRef.current = true;
    setSaving(true);
    setStatus({ kind: "idle" });
    try {
      if (saved) {
        const changes = categoryChanges(saved, values);
        if (Object.keys(changes).length === 0) return;
        const updated = await updateAdminCategory(saved.id, changes);
        setSaved(updated);
        setValues(categoryToValues(updated));
        setStatus({ kind: "saved" });
        onSaved?.(updated);
      } else {
        setCreated(await createAdminCategory(categoryCreateInput(values)));
      }
    } catch (failure) {
      const fieldErrors = serverFieldErrors(failure, CATEGORY_FIELDS);
      setErrors(fieldErrors);
      focusAfterSave.current = CATEGORY_FIELD_ORDER.find((field) => fieldErrors[field]) ?? null;
      setStatus({ kind: "error", message: getApiErrorMessage(failure, "We couldn't save the category. Please try again.") });
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
          Category &quot;{created.name}&quot; created.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="primary" size="sm">
            <Link href={`/admin/categories/${created.id}`}>Open it</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/admin/categories">Back to categories</Link>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setCreated(null);
              setValues(EMPTY_CATEGORY);
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

  const setRef = (field: CategoryField) => (element: HTMLInputElement | HTMLTextAreaElement | null) => {
    refs.current[field] = element;
  };

  return (
    <form onSubmit={submit} noValidate className="flex max-w-2xl flex-col gap-5 rounded-2xl border border-border bg-card p-6 shadow-card">
      {status.kind === "error" ? <Banner>{status.message}</Banner> : null}
      {status.kind === "saved" ? (
        <p role="status" className="flex items-center gap-2 text-sm font-medium text-primary">
          <Check className="h-4 w-4" aria-hidden="true" />
          Saved.
        </p>
      ) : null}

      <FormField id="category-name" label="Name" required error={errors.name}>
        <Input name="name" ref={setRef("name")} value={values.name} onChange={(e) => edit("name", e.target.value)} disabled={saving} maxLength={100} />
      </FormField>
      <FormField
        id="category-slug"
        label="Slug"
        required={editing}
        error={errors.slug}
        hint={editing ? "Part of the category's web address. Changing it changes the link." : "Leave empty to make one from the name."}
      >
        <Input name="slug" ref={setRef("slug")} value={values.slug} onChange={(e) => edit("slug", e.target.value)} disabled={saving} maxLength={120} />
      </FormField>
      <FormField id="category-description" label="Description" error={errors.description}>
        <Textarea name="description" ref={setRef("description")} value={values.description} onChange={(e) => edit("description", e.target.value)} disabled={saving} maxLength={2000} />
      </FormField>
      <FormField id="category-image" label="Image address" error={errors.image_url} hint="An https:// address, or a path on this site such as /images/oats.jpg.">
        <Input name="image_url" ref={setRef("image_url")} value={values.image_url} onChange={(e) => edit("image_url", e.target.value)} disabled={saving} maxLength={500} />
      </FormField>

      {!editing ? (
        <label className="flex items-center gap-3 text-sm text-foreground">
          <Checkbox checked={values.is_active} onChange={(e) => edit("is_active", e.target.checked)} disabled={saving} />
          Show this category in the shop
        </label>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" disabled={saving || (editing && !dirty)}>
          {saving ? "Saving..." : editing ? "Save changes" : "Create category"}
        </Button>
        {editing && dirty ? (
          <Button
            type="button"
            variant="ghost"
            disabled={saving}
            onClick={() => {
              if (saved) setValues(categoryToValues(saved));
              setErrors({});
              setStatus({ kind: "idle" });
            }}
          >
            Discard changes
          </Button>
        ) : null}
        <Button asChild variant="ghost">
          <Link href="/admin/categories">Back to categories</Link>
        </Button>
      </div>
    </form>
  );
}
