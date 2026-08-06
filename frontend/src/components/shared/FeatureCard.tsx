import { iconMap } from "@/lib/icon-map";
import type { Feature } from "@/types";

interface FeatureCardProps {
  feature: Feature;
}

export function FeatureCard({ feature }: FeatureCardProps) {
  const Icon = iconMap[feature.icon] ?? iconMap.Leaf;

  return (
    <div className="flex flex-col items-start gap-4 rounded-2xl border border-border bg-card p-6 shadow-card transition-shadow duration-300 hover:shadow-lift">
      <span className="flex h-14 w-14 items-center justify-center rounded-blob bg-accent/10 text-accent">
        <Icon className="h-7 w-7" strokeWidth={1.75} />
      </span>
      <h3 className="font-display text-lg font-semibold text-foreground">{feature.title}</h3>
      <p className="text-sm text-muted-foreground">{feature.description}</p>
    </div>
  );
}
