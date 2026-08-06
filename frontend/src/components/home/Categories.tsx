import { CategoryCard } from "@/components/shared/CategoryCard";
import { SectionTitle } from "@/components/shared/SectionTitle";
import { categories } from "@/lib/placeholder-data";

export function Categories() {
  return (
    <section className="py-16 lg:py-24">
      <div className="container flex flex-col gap-10">
        <SectionTitle
          eyebrow="Shop by category"
          title="Everything your pantry needs"
          description="Eight staple categories, each sourced and packed with the same standard of freshness."
        />

        <div className="-mx-5 flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-pl-5 px-5 pb-2 scrollbar-none sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0 lg:grid-cols-4">
          {categories.map((category) => (
            <CategoryCard key={category.id} category={category} />
          ))}
        </div>
      </div>
    </section>
  );
}
