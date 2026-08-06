import { Star } from "lucide-react";

import { SectionTitle } from "@/components/shared/SectionTitle";
import { testimonials } from "@/lib/placeholder-data";

export function Testimonials() {
  return (
    <section className="bg-primary-light/40 py-16 lg:py-24">
      <div className="container flex flex-col gap-10">
        <SectionTitle
          eyebrow="Customer stories"
          title="Loved by kitchens everywhere"
          description="A few words from the households who order from us every month."
        />

        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
          {testimonials.map((testimonial) => (
            <figure
              key={testimonial.id}
              className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-6 shadow-card"
            >
              <div className="flex items-center gap-0.5">
                {Array.from({ length: 5 }).map((_, index) => (
                  <Star
                    key={index}
                    className={
                      index < testimonial.rating
                        ? "h-4 w-4 fill-secondary text-secondary"
                        : "h-4 w-4 text-border"
                    }
                  />
                ))}
              </div>

              <blockquote className="text-sm text-foreground/90">
                &ldquo;{testimonial.quote}&rdquo;
              </blockquote>

              <figcaption className="mt-auto flex items-center gap-3 pt-2">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                  {testimonial.initials}
                </span>
                <span className="flex flex-col">
                  <span className="text-sm font-semibold text-foreground">{testimonial.name}</span>
                  <span className="text-xs text-muted-foreground">{testimonial.location}</span>
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  );
}
