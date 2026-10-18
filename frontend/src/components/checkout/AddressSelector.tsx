import type { Address } from "@/types/address";

interface AddressSelectorProps {
  addresses: Address[];
  selectedId: string | null;
  disabled?: boolean;
  onSelect: (id: string) => void;
}

/** The user's saved addresses as a radio group; one is chosen for delivery. */
export function AddressSelector({ addresses, selectedId, disabled = false, onSelect }: AddressSelectorProps) {
  return (
    <fieldset disabled={disabled} className="flex flex-col gap-3">
      <legend className="sr-only">Choose a delivery address</legend>
      {addresses.map((address) => {
        const selected = address.id === selectedId;
        return (
          <label
            key={address.id}
            className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 text-sm transition-colors ${
              selected ? "border-primary bg-primary-light" : "border-border bg-card hover:bg-muted"
            }`}
          >
            <input
              type="radio"
              name="shipping-address"
              value={address.id}
              checked={selected}
              onChange={() => onSelect(address.id)}
              className="mt-1 h-4 w-4 accent-primary"
            />
            <span className="flex flex-col gap-0.5">
              <span className="font-medium text-foreground">
                {address.full_name}
                {address.is_default ? (
                  <span className="ml-2 rounded-full bg-secondary-light px-2 py-0.5 text-xs font-medium text-foreground">
                    Default
                  </span>
                ) : null}
              </span>
              <span className="text-muted-foreground">
                {address.address_line_1}
                {address.address_line_2 ? `, ${address.address_line_2}` : ""}
              </span>
              <span className="text-muted-foreground">
                {address.city}, {address.state} {address.postal_code}
              </span>
              <span className="text-muted-foreground">Phone: {address.phone_number}</span>
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}
