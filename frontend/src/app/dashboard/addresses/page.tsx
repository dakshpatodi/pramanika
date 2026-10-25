"use client";

import { useState } from "react";
import { Check, MapPin } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AddressForm } from "@/components/checkout/AddressForm";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { SavedAddressCard } from "@/components/dashboard/SavedAddressCard";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAddresses } from "@/hooks/useAddresses";
import { MAX_ADDRESSES, diffAddress } from "@/lib/address-validation";
import { getApiErrorMessage } from "@/lib/errors";
import type { AddressInput } from "@/types/address";

type Mode = { kind: "none" } | { kind: "add" } | { kind: "edit"; id: string } | { kind: "delete"; id: string };
type Notice = { kind: "success" | "error"; text: string } | null;

function AddressesContent() {
  const { addresses, isLoading, loadError, reload, addAddress, updateAddress, makeDefault, removeAddress } = useAddresses();
  const [mode, setMode] = useState<Mode>({ kind: "none" });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  async function run(id: string, action: () => Promise<void>, success: string, fallback: string) {
    if (busyId) return;
    setBusyId(id);
    setNotice(null);
    try {
      await action();
      setMode({ kind: "none" });
      setNotice({ kind: "success", text: success });
    } catch (error) {
      setNotice({ kind: "error", text: getApiErrorMessage(error, fallback) });
    } finally {
      setBusyId(null);
    }
  }

  let body: React.ReactNode;
  if (!addresses && loadError) {
    body = (
      <Card className="flex flex-col items-center gap-4 px-6 py-14 text-center">
        <p role="alert" className="max-w-sm text-foreground">
          {loadError}
        </p>
        <Button variant="primary" onClick={() => void reload()} disabled={isLoading}>
          {isLoading ? "Retrying..." : "Try again"}
        </Button>
      </Card>
    );
  } else if (!addresses) {
    body = (
      <div role="status" aria-label="Loading your addresses" className="flex flex-col gap-4">
        {[0, 1].map((n) => (
          <div key={n} className="h-36 animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>
    );
  } else {
    const isEmpty = addresses.length === 0;
    const adding = mode.kind === "add" || (isEmpty && mode.kind === "none");
    const atLimit = addresses.length >= MAX_ADDRESSES;

    body = (
      <div className="flex flex-col gap-5">
        <div aria-live="polite">
          {notice?.kind === "success" ? (
            <p role="status" className="flex items-center gap-2 text-sm font-medium text-primary">
              <Check className="h-4 w-4" aria-hidden="true" /> {notice.text}
            </p>
          ) : null}
        </div>
        {notice?.kind === "error" ? <Banner>{notice.text}</Banner> : null}

        {isEmpty ? (
          <div className="flex flex-col items-center gap-2 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-blob bg-primary-light text-primary">
              <MapPin className="h-7 w-7" aria-hidden="true" />
            </span>
            <h2 className="font-display text-xl font-semibold text-foreground">No saved addresses yet</h2>
            <p className="max-w-sm text-sm text-muted-foreground">Add one now and it will be ready at checkout.</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-4">
            {addresses.map((address) => (
              <li key={address.id}>
                {mode.kind === "edit" && mode.id === address.id ? (
                  <Card className="p-5">
                    <h2 className="mb-4 font-display text-lg font-semibold text-foreground">Edit address</h2>
                    <AddressForm
                      offerDefault={false}
                      initial={address}
                      submitLabel="Save changes"
                      ariaLabel="Edit address"
                      autoFocus
                      onCancel={() => setMode({ kind: "none" })}
                      onSubmit={async (input: AddressInput) => {
                        const changes = diffAddress(address, input);
                        if (Object.keys(changes).length === 0) {
                          setMode({ kind: "none" });
                          setNotice({ kind: "success", text: "No changes to save." });
                          return;
                        }
                        await updateAddress(address.id, changes);
                        setMode({ kind: "none" });
                        setNotice({ kind: "success", text: "Address updated." });
                      }}
                    />
                  </Card>
                ) : (
                  <SavedAddressCard
                    address={address}
                    isBusy={busyId === address.id}
                    isConfirmingDelete={mode.kind === "delete" && mode.id === address.id}
                    onEdit={() => {
                      setNotice(null);
                      setMode({ kind: "edit", id: address.id });
                    }}
                    onSetDefault={() =>
                      void run(address.id, () => makeDefault(address.id), "Default address updated.", "We couldn't change your default address. Please try again.")
                    }
                    onAskDelete={() => {
                      setNotice(null);
                      setMode({ kind: "delete", id: address.id });
                    }}
                    onConfirmDelete={() =>
                      void run(address.id, () => removeAddress(address.id), "Address deleted.", "We couldn't delete this address. Please try again.")
                    }
                    onCancelDelete={() => setMode({ kind: "none" })}
                  />
                )}
              </li>
            ))}
          </ul>
        )}

        {adding ? (
          <Card className="p-5">
            <h2 className="mb-4 font-display text-lg font-semibold text-foreground">
              {isEmpty ? "Add your first address" : "Add a new address"}
            </h2>
            <AddressForm
              offerDefault={!isEmpty}
              autoFocus={!isEmpty}
              onCancel={isEmpty ? undefined : () => setMode({ kind: "none" })}
              onSubmit={async (input) => {
                await addAddress(input);
                setMode({ kind: "none" });
                setNotice({ kind: "success", text: "Address added." });
              }}
            />
          </Card>
        ) : atLimit ? (
          <p className="text-sm text-muted-foreground">
            You have saved the maximum of {MAX_ADDRESSES} addresses. Delete one to add another.
          </p>
        ) : (
          <div>
            <Button
              variant="primary"
              onClick={() => {
                setNotice(null);
                setMode({ kind: "add" });
              }}
            >
              Add address
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <DashboardShell title="Saved addresses" description="Where we deliver. Changing one never changes an order you already placed.">
      {body}
    </DashboardShell>
  );
}

export default function SavedAddressesPage() {
  return (
    <ProtectedRoute>
      <AddressesContent />
    </ProtectedRoute>
  );
}
