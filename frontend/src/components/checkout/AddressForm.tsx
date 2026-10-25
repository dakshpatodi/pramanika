"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  toAddressInput,
  validateAddress,
  type AddressErrors,
  type AddressField,
} from "@/lib/address-validation";
import { getApiErrorMessage } from "@/lib/errors";
import type { Address, AddressInput } from "@/types/address";

interface AddressFormProps {
  /** Saves the address. Should REJECT on failure - the message is shown in the form. */
  onSubmit: (input: AddressInput) => Promise<unknown>;
  /** Shown only when there are other addresses to go back to. */
  onCancel?: () => void;
  /** Offer "make this my default" (hidden for the very first address - it is always the default). */
  offerDefault: boolean;
  /** Edit mode: start from this saved address instead of an empty form. */
  initial?: Address;
  /** Button text; "Save address" by default. */
  submitLabel?: string;
  /** Accessible name of the form; "Add a delivery address" by default. */
  ariaLabel?: string;
  /** Put the cursor in the first field when the form appears. */
  autoFocus?: boolean;
}

const EMPTY = {
  full_name: "",
  phone_number: "",
  address_line_1: "",
  address_line_2: "",
  city: "",
  state: "",
  postal_code: "",
};

const FIELDS: { name: AddressField; label: string; autoComplete: string; inputMode?: "tel" | "numeric"; required: boolean }[] = [
  { name: "full_name", label: "Full name", autoComplete: "name", required: true },
  { name: "phone_number", label: "Phone number", autoComplete: "tel", inputMode: "tel", required: true },
  { name: "address_line_1", label: "Address line 1", autoComplete: "address-line1", required: true },
  { name: "address_line_2", label: "Address line 2 (optional)", autoComplete: "address-line2", required: false },
  { name: "city", label: "City", autoComplete: "address-level2", required: true },
  { name: "state", label: "State", autoComplete: "address-level1", required: true },
  { name: "postal_code", label: "PIN code", autoComplete: "postal-code", inputMode: "numeric", required: true },
];

/** Inline address form - add a new one, or edit a saved one with `initial` (India only for now). */
export function AddressForm({
  onSubmit,
  onCancel,
  offerDefault,
  initial,
  submitLabel = "Save address",
  ariaLabel = "Add a delivery address",
  autoFocus = false,
}: AddressFormProps) {
  const [values, setValues] = useState(() =>
    initial
      ? {
          full_name: initial.full_name,
          phone_number: initial.phone_number,
          address_line_1: initial.address_line_1,
          address_line_2: initial.address_line_2 ?? "",
          city: initial.city,
          state: initial.state,
          postal_code: initial.postal_code,
        }
      : EMPTY
  );
  const [isDefault, setIsDefault] = useState(false);
  const [errors, setErrors] = useState<AddressErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isSaving) return;
    setServerError(null);

    const found = validateAddress(values);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setIsSaving(true);
    try {
      await onSubmit(toAddressInput(values, offerDefault && isDefault));
    } catch (error) {
      setServerError(getApiErrorMessage(error, "We couldn't save this address. Please try again."));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} noValidate aria-label={ariaLabel} className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {FIELDS.map((field, index) => {
          const id = `address-${field.name}`;
          const error = errors[field.name];
          return (
            <div key={field.name} className={`flex flex-col gap-1.5 ${field.name === "address_line_1" || field.name === "address_line_2" ? "sm:col-span-2" : ""}`}>
              <label htmlFor={id} className="text-sm font-medium text-foreground">
                {field.label}
              </label>
              <Input
                id={id}
                name={field.name}
                value={values[field.name]}
                autoComplete={field.autoComplete}
                inputMode={field.inputMode}
                required={field.required}
                invalid={Boolean(error)}
                aria-describedby={error ? `${id}-error` : undefined}
                disabled={isSaving}
                autoFocus={autoFocus && index === 0}
                onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
              />
              {error ? (
                <p id={`${id}-error`} className="text-xs text-accent-dark">
                  {error}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>

      {offerDefault ? (
        <label className="flex items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            checked={isDefault}
            disabled={isSaving}
            onChange={(e) => setIsDefault(e.target.checked)}
            className="h-4 w-4 accent-primary"
          />
          Make this my default address
        </label>
      ) : null}

      {serverError ? (
        <p role="alert" className="text-sm text-accent-dark">
          {serverError}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="primary" disabled={isSaving}>
          {isSaving ? "Saving..." : submitLabel}
        </Button>
        {onCancel ? (
          <Button type="button" variant="ghost" disabled={isSaving} onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
    </form>
  );
}
