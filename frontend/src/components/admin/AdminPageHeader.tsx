interface AdminPageHeaderProps {
  title: string;
  description?: string;
  /** Buttons on the right (e.g. Refresh, New product). */
  actions?: React.ReactNode;
}

/** The one visible heading of an admin page, with optional actions. */
export function AdminPageHeader({ title, description, actions }: AdminPageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="font-display text-3xl font-semibold text-foreground">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
