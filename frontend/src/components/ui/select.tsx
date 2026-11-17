import * as React from "react";

import { cn } from "@/lib/utils";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}

/** A native <select> styled like Input (keyboard and screen-reader behaviour come from the browser). */
const Select = React.forwardRef<HTMLSelectElement, SelectProps>(({ className, invalid, ...props }, ref) => (
  <select
    ref={ref}
    aria-invalid={invalid || undefined}
    className={cn(
      "h-11 w-full rounded-xl border bg-card px-3 text-sm text-foreground transition-colors",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background",
      "disabled:cursor-not-allowed disabled:opacity-50",
      invalid ? "border-accent" : "border-border",
      className
    )}
    {...props}
  />
));
Select.displayName = "Select";

export { Select };
