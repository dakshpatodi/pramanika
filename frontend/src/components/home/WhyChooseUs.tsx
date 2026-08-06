import { FeatureCard } from "@/components/shared/FeatureCard";
import { SectionTitle } from "@/components/shared/SectionTitle";
import { features } from "@/lib/placeholder-data";

export function WhyChooseUs() {
  return (
    <section className="py-16 lg:py-24">
      <div className="container flex flex-col gap-10">
        <SectionTitle
          eyebrow="Why Pramanika"
          title="Quality you can taste"
          description="Four commitments we don't compromise on, order after order."
        />

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((feature) => (
            <FeatureCard key={feature.id} feature={feature} />
          ))}
        </div>
      </div>
    </section>
  );
}
