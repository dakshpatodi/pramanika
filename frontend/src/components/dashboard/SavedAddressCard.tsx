import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { Address } from "@/types/address";

interface SavedAddressCardProps {
  address: Address;
  /** A change to this address is being saved: its buttons wait. */
  isBusy: boolean;
  /** Showing "Delete this address?" instead of the normal buttons. */
  isConfirmingDelete: boolean;
  onEdit: () => void;
  onSetDefault: () => void;
  onAskDelete: () => void;
  onConfirmDelete: () => void;
  onCancelDelete: () => void;
}

/** One saved address with its actions. Button names include the address so
 * a screen reader can tell "Edit" on one card from "Edit" on another. */
export function SavedAddressCard({
  address,
  isBusy,
  isConfirmingDelete,
  onEdit,
  onSetDefault,
  onAskDelete,
  onConfirmDelete,
  onCancelDelete,
}: SavedAddressCardProps) {
  const label = `${address.full_name}, ${address.address_line_1}`;

  return (
    <Card role="group" aria-label={`Address: ${label}`} className="flex flex-col gap-4 p-5">
      <address className="flex flex-col gap-0.5 text-sm not-italic text-foreground">
        <span className="flex flex-wrap items-center gap-2 font-medium">
          {address.full_name}
          {address.is_default ? (
            <span className="rounded-full bg-secondary-light px-2 py-0.5 text-xs font-medium text-foreground">Default</span>
          ) : null}
        </span>
        <span>
          {address.address_line_1}
          {address.address_line_2 ? `, ${address.address_line_2}` : ""}
        </span>
        <span>
          {address.city}, {address.state} {address.postal_code}
        </span>
        <span>{address.country}</span>
        <span className="text-muted-foreground">Phone: {address.phone_number}</span>
      </address>

      {isConfirmingDelete ? (
        <div className="flex flex-col gap-3 rounded-xl bg-muted p-4 text-sm">
          <p className="text-foreground">
            Delete this address? Orders you have already placed keep their delivery details.
            {address.is_default ? " Another saved address will become your default." : ""}
          </p>
          <div className="flex flex-wrap gap-3">
            <Button variant="accent" size="sm" disabled={isBusy} onClick={onConfirmDelete}>
              {isBusy ? "Deleting..." : "Yes, delete"}
            </Button>
            <Button variant="ghost" size="sm" disabled={isBusy} onClick={onCancelDelete}>
              Keep address
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled={isBusy} onClick={onEdit} aria-label={`Edit address: ${label}`}>
            Edit
          </Button>
          {address.is_default ? null : (
            <Button
              variant="outline"
              size="sm"
              disabled={isBusy}
              onClick={onSetDefault}
              aria-label={`Make default: ${label}`}
            >
              {isBusy ? "Saving..." : "Make default"}
            </Button>
          )}
          <Button variant="ghost" size="sm" disabled={isBusy} onClick={onAskDelete} aria-label={`Delete address: ${label}`}>
            Delete
          </Button>
        </div>
      )}
    </Card>
  );
}
