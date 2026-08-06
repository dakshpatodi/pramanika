import { Button } from "@/components/ui/button";
import { ProductCard } from "@/components/shared/ProductCard";
import { SectionTitle } from "@/components/shared/SectionTitle";
import { products } from "@/lib/placeholder-data";

export function FeaturedProducts() {
  return (
    <section className="bg-muted/50 py-16 lg:py-24">
      <div className="container flex flex-col gap-10">
        <SectionTitle
          eyebrow="Featured products"
          title="This week's picks"
          description="A rotating shortlist of what's freshest in stock right now."
        />

        <div className="grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4">
          {products.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>

        <div className="flex justify-center">
          <Button variant="outline" size="lg">
            View All Products
          </Button>
        </div>
      </div>
    </section>
  );
}
