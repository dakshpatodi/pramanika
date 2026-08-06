import { cn } from "@/lib/utils";

interface SectionTitleProps {
  eyebrow?: string;
  title: string;
  description?: string;
  align?: "left" | "center";
  className?: string;
}

/**
 * Standard heading block for a homepage section: small eyebrow label,
 * a display-face title (with the last word styled in primary italic
 * for a consistent brand accent), and an optional supporting sentence.
 */
export function SectionTitle({
  eyebrow,
  title,
  description,
  align = "center",
  className,
}: SectionTitleProps) {
  const words = title.trim().split(" ");
  const lastWord = words.pop();
  const leadingWords = words.join(" ");

  return (
    <div
      className={cn(
        "flex flex-col gap-3",
        align === "center" ? "items-center text-center" : "items-start text-left",
        className
      )}
    >
      {eyebrow ? (
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
          {eyebrow}
        </span>
      ) : null}
      <h2 className="max-w-2xl text-3xl font-semibold leading-tight text-foreground sm:text-4xl">
        {leadingWords ? `${leadingWords} ` : ""}
        <em className="font-medium italic text-primary">{lastWord}</em>
      </h2>
      {description ? (
        <p className="max-w-xl text-base text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}
