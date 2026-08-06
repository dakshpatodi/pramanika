"use client";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { Leaf, Menu, Search, ShoppingCart, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navLinks = [
  { label: "Home", href: "/" },
  { label: "Shop", href: "/shop" },
  { label: "Categories", href: "/categories" },
  { label: "About", href: "/about" },
  { label: "Contact", href: "/contact" },
];

export function Navbar() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-border/80 bg-background/90 backdrop-blur">
      <div className="container flex items-center justify-between py-4">
        <Link href="/" className="flex items-center gap-2" onClick={() => setIsMenuOpen(false)}>
          <span className="flex h-10 w-10 items-center justify-center rounded-blob bg-primary text-primary-foreground overflow-hidden">
             <Image 
                src="/pramanika-logo.jpg" 
                alt="Logo" 
                width={60} 
                height={60} 
                className="object-contain" 
                />
          </span>
          <span className="font-display text-lg font-semibold text-foreground">
            Pramanika
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden items-center gap-8 lg:flex">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-foreground/80 transition-colors hover:text-primary"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-1.5 sm:gap-2">
          <Button variant="ghost" size="icon" aria-label="Search products" className="hidden sm:inline-flex">
            <Search />
          </Button>
          <Button variant="ghost" size="icon" aria-label="View cart">
            <ShoppingCart />
          </Button>
          <Button variant="primary" size="md" className="hidden sm:inline-flex">
            Login
          </Button>

          {/* Mobile menu toggle */}
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label={isMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={isMenuOpen}
            onClick={() => setIsMenuOpen((open) => !open)}
          >
            {isMenuOpen ? <X /> : <Menu />}
          </Button>
        </div>
      </div>

      {/* Mobile nav panel */}
      <div
        className={cn(
          "overflow-hidden border-t border-border/80 bg-background transition-[max-height] duration-300 lg:hidden",
          isMenuOpen ? "max-h-96" : "max-h-0 border-t-0"
        )}
      >
        <nav className="container flex flex-col gap-1 py-3">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-lg px-3 py-2.5 text-sm font-medium text-foreground/80 transition-colors hover:bg-muted hover:text-primary"
              onClick={() => setIsMenuOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          <Button variant="primary" size="md" className="mt-2 w-full sm:hidden">
            Login
          </Button>
        </nav>
      </div>
    </header>
  );
}
