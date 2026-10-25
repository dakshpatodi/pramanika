"use client";

import { useRef, useState } from "react";
import { Check } from "lucide-react";

import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import {
  NAME_MAX_LENGTH,
  changedFields,
  validateProfile,
  valuesFromUser,
  type ProfileErrors,
  type ProfileField,
  type ProfileValues,
} from "@/lib/profile-validation";
import { updateProfile } from "@/services/profile";

type Status = { kind: "idle" } | { kind: "saved" } | { kind: "error"; message: string };

const FIELD_ORDER: ProfileField[] = ["first_name", "last_name", "phone_number"];

/**
 * Edit the fields a customer may change: first name, last name, phone.
 * The email is shown but locked (it is the login identity); role and account
 * flags are not on this form at all and the server refuses them anyway.
 *
 * Only the changed fields are sent. On success the signed-in user in
 * AuthContext is replaced with the server's copy so the Navbar updates.
 */
export function ProfileForm() {
  const { user, updateUser } = useAuth();
  const [values, setValues] = useState<ProfileValues>(() => (user ? valuesFromUser(user) : { first_name: "", last_name: "", phone_number: "" }));
  const [errors, setErrors] = useState<ProfileErrors>({});
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [isSaving, setIsSaving] = useState(false);

  const savingRef = useRef(false); // blocks a double submit before React re-renders
  const inputRefs = useRef<Partial<Record<ProfileField, HTMLInputElement | null>>>({});

  if (!user) return null;

  const changes = changedFields(user, values);
  const hasChanges = Object.keys(changes).length > 0;

  function edit(field: ProfileField, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => (current[field] ? { ...current, [field]: undefined } : current));
    setStatus((current) => (current.kind === "idle" ? current : { kind: "idle" }));
  }

  function discard() {
    if (!user) return;
    setValues(valuesFromUser(user));
    setErrors({});
    setStatus({ kind: "idle" });
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user || savingRef.current) return;

    const found = validateProfile(values);
    setErrors(found);
    const firstInvalid = FIELD_ORDER.find((field) => found[field]);
    if (firstInvalid) {
      inputRefs.current[firstInvalid]?.focus();
      return;
    }
    if (!hasChanges) return;

    savingRef.current = true;
    setIsSaving(true);
    setStatus({ kind: "idle" });
    try {
      const updated = await updateProfile(changes);
      updateUser(updated);
      setValues(valuesFromUser(updated));
      setStatus({ kind: "saved" });
    } catch (error) {
      // Keep what the user typed so they can fix it; the server's own message says what was wrong.
      setStatus({ kind: "error", message: getApiErrorMessage(error, "We couldn't save your changes. Please try again.") });
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  }

  function field(name: ProfileField, label: string, extra: React.InputHTMLAttributes<HTMLInputElement>) {
    const errorId = `profile-${name}-error`;
    return (
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`profile-${name}`}>{label}</Label>
        <Input
          id={`profile-${name}`}
          name={name}
          ref={(element) => {
            inputRefs.current[name] = element;
          }}
          value={values[name]}
          onChange={(event) => edit(name, event.target.value)}
          invalid={Boolean(errors[name])}
          aria-describedby={errors[name] ? errorId : undefined}
          disabled={isSaving}
          {...extra}
        />
        {errors[name] ? (
          <p id={errorId} className="text-xs text-accent-dark">
            {errors[name]}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Edit profile" className="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {field("first_name", "First name", { autoComplete: "given-name", maxLength: NAME_MAX_LENGTH + 20 })}
        {field("last_name", "Last name", { autoComplete: "family-name", maxLength: NAME_MAX_LENGTH + 20 })}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="profile-email">Email</Label>
        <Input id="profile-email" value={user.email} readOnly aria-describedby="profile-email-hint" className="bg-muted" />
        <p id="profile-email-hint" className="text-xs text-muted-foreground">
          Your email is your login, so it can&apos;t be changed here.
        </p>
      </div>

      {field("phone_number", "Phone number", { type: "tel", autoComplete: "tel", inputMode: "tel", placeholder: "+919876543210" })}

      {status.kind === "error" ? <Banner>{status.message}</Banner> : null}
      {status.kind === "saved" ? (
        <p role="status" className="flex items-center gap-2 text-sm font-medium text-primary">
          <Check className="h-4 w-4" aria-hidden="true" /> Profile updated.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" disabled={!hasChanges || isSaving}>
          {isSaving ? "Saving..." : "Save changes"}
        </Button>
        {hasChanges && !isSaving ? (
          <Button type="button" variant="ghost" onClick={discard}>
            Discard changes
          </Button>
        ) : null}
      </div>
    </form>
  );
}
