"use client";

import { motion } from "framer-motion";
import { ArrowRight, Leaf, Sprout, Wheat } from "lucide-react";

import { Button } from "@/components/ui/button";

const stats = [
  { value: "500+", label: "Wholesome products" },
  { value: "12,000+", label: "Happy households" },
  { value: "48 hr", label: "Farm-to-door dispatch" },
];

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="container grid items-center gap-12 py-16 lg:grid-cols-[1.1fr_0.9fr] lg:py-24">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="flex flex-col items-start gap-6"
        >
          <span className="rounded-full bg-primary-light px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            Whole foods, honestly sourced
          </span>

          <h1 className="max-w-xl font-display text-4xl font-semibold leading-[1.1] text-foreground sm:text-5xl lg:text-6xl">
            Real grains, ready mixes &amp; pantry staples that taste like{" "}
            <em className="font-medium italic text-primary">home</em>
          </h1>

          <p className="max-w-lg text-base text-muted-foreground sm:text-lg">
            From millets and pulses to dry fruits and spices - Pramanika brings small-batch,
            preservative-free staples straight from source to your kitchen shelf.
          </p>

          <div className="flex flex-col gap-3 sm:flex-row">
            <Button size="lg" variant="primary">
              Shop Now <ArrowRight className="h-4 w-4" />
            </Button>
            <Button size="lg" variant="outline">
              Explore Categories
            </Button>
          </div>

          <dl className="mt-4 grid grid-cols-3 gap-6 border-t border-border pt-6">
            {stats.map((stat) => (
              <div key={stat.label} className="flex flex-col gap-1">
                <dt className="font-display text-xl font-semibold text-foreground sm:text-2xl">
                  {stat.value}
                </dt>
                <dd className="text-xs text-muted-foreground sm:text-sm">{stat.label}</dd>
              </div>
            ))}
          </dl>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7, ease: "easeOut", delay: 0.15 }}
          className="relative mx-auto flex h-80 w-full max-w-md items-center justify-center sm:h-96 lg:h-[26rem]"
        >
          <div className="absolute inset-0 rounded-blob bg-primary-light" />
          <div className="absolute -right-4 -top-4 h-24 w-24 rounded-blob bg-secondary/30 animate-float" />
          <div
            className="absolute -bottom-6 left-2 h-28 w-28 rounded-blob bg-accent/20 animate-float"
            style={{ animationDelay: "1.2s" }}
          />

          <div className="relative flex h-48 w-48 items-center justify-center rounded-blob bg-primary shadow-lift sm:h-56 sm:w-56">
            <Wheat className="h-24 w-24 text-primary-foreground" strokeWidth={1.25} />
          </div>

          <motion.span
            className="absolute left-2 top-6 flex h-16 w-16 items-center justify-center rounded-blob bg-secondary text-secondary-foreground shadow-lift sm:h-20 sm:w-20"
            animate={{ y: [0, -10, 0] }}
            transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
          >
            <Sprout className="h-8 w-8 sm:h-9 sm:w-9" strokeWidth={1.5} />
          </motion.span>

          <motion.span
            className="absolute bottom-4 right-0 flex h-14 w-14 items-center justify-center rounded-blob bg-accent text-accent-foreground shadow-lift sm:h-16 sm:w-16"
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 4.5, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
          >
            <Leaf className="h-6 w-6 sm:h-7 sm:w-7" strokeWidth={1.5} />
          </motion.span>
        </motion.div>
      </div>
    </section>
  );
}
