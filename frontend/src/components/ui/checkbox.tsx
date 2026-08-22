import * as React from "react";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export type CheckboxProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">;

/**
 * Styled native checkbox (no @radix-ui/react-checkbox dependency needed
 * for something this simple). `appearance-none` strips the browser's
 * default checkbox rendering; the check icon is layered on top and
 * shown/hidden via the `peer-checked` variant rather than JS state, so
 * this works as an uncontrolled input - react-hook-form's `register()`
 * can attach directly to it like any other native form field.
 */
const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, ...props }, ref) => (
    <span className="relative inline-flex h-5 w-5 shrink-0 items-center justify-center">
      <input
        ref={ref}
        type="checkbox"
        className={cn(
          "peer h-5 w-5 shrink-0 cursor-pointer appearance-none rounded-md border border-border bg-card transition-colors",
          "checked:border-primary checked:bg-primary",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        {...props}
      />
      <Check
        className="pointer-events-none absolute h-3.5 w-3.5 text-primary-foreground opacity-0 peer-checked:opacity-100"
        strokeWidth={3}
      />
    </span>
  )
);
Checkbox.displayName = "Checkbox";

export { Checkbox };