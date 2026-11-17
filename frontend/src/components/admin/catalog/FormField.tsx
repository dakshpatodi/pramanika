import { cloneElement, isValidElement } from "react";

import { Label } from "@/components/ui/label";

interface FormFieldProps {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  /** One control (Input, Select, Textarea). It receives the id, aria-describedby and the invalid state. */
  children: React.ReactElement<Record<string, unknown>>;
}

/** A label, one control, an optional hint and an error - wired together for screen readers. */
export function FormField({ id, label, error, hint, required, children }: FormFieldProps) {
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(" ") || undefined;
  const control = isValidElement(children)
    ? cloneElement(children, { id, "aria-describedby": describedBy, invalid: Boolean(error), "aria-required": required || undefined })
    : children;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </Label>
      {control}
      {hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-xs text-accent-dark">
          {error}
        </p>
      ) : null}
    </div>
  );
}
