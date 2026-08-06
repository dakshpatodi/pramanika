"use client";

import { useState } from "react";
import { Mail } from "lucide-react";

import { Button } from "@/components/ui/button";

export function Newsletter() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  // Phase 1: presentational only. No email service is wired up yet -
  // this just gives the form a working, accessible interaction state.
  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email) return;
    setSubmitted(true);
    setEmail("");
  }

  return (
    <section className="py-16 lg:py-24">
      <div className="container">
        <div className="flex flex-col items-center gap-6 rounded-3xl bg-primary px-6 py-14 text-center sm:px-12">
          <span className="flex h-14 w-14 items-center justify-center rounded-blob bg-primary-foreground/15 text-primary-foreground">
            <Mail className="h-6 w-6" />
          </span>

          <h2 className="max-w-lg font-display text-2xl font-semibold text-primary-foreground sm:text-3xl">
            Get fresh harvest updates in your inbox
          </h2>
          <p className="max-w-md text-sm text-primary-foreground/80">
            New arrivals, seasonal recipes, and early access to sales - once or twice a month, nothing more.
          </p>

          <form
            onSubmit={handleSubmit}
            className="flex w-full max-w-md flex-col gap-3 sm:flex-row"
            noValidate
          >
            <label htmlFor="newsletter-email" className="sr-only">
              Email address
            </label>
            <input
              id="newsletter-email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              className="h-12 flex-1 rounded-full border-0 bg-primary-foreground px-5 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary focus-visible:ring-offset-2 focus-visible:ring-offset-primary"
            />
            <Button type="submit" variant="secondary" size="lg">
              Subscribe
            </Button>
          </form>

          <p role="status" className="text-xs text-primary-foreground/90" aria-live="polite">
            {submitted ? "Thanks for subscribing! Check your inbox for a confirmation soon." : ""}
          </p>
        </div>
      </div>
    </section>
  );
}
