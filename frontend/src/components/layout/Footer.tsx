import Image from "next/image";
import Link from "next/link";
import { Facebook, Instagram, Leaf, Mail, MapPin, Phone, Twitter } from "lucide-react";

const quickLinks = [
  { label: "Home", href: "/" },
  { label: "Shop", href: "/shop" },
  { label: "Categories", href: "/categories" },
  { label: "About Us", href: "/about" },
  { label: "Contact", href: "/contact" },
];

const socialLinks = [
  { label: "Facebook", href: "#", icon: Facebook },
  { label: "Instagram", href: "#", icon: Instagram },
  { label: "Twitter", href: "#", icon: Twitter },
];

export function Footer() {
  return (
    <footer className="border-t border-border bg-primary-light/40">
      <div className="container grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col gap-4">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-blob bg-primary text-primary-foreground overflow-hidden">
                <Image 
                  src="/pramanika-logo.jpg" 
                  alt="Logo" 
                  width={50} 
                  height={50} 
                  className="object-contain" 
                  />
            </span>
            <span className="font-display text-lg font-semibold text-foreground">
              Pramanika
            </span>
          </Link>
          <p className="max-w-xs text-sm text-muted-foreground">
            Whole grains, millets, and pantry staples sourced with care - fresh from the
            harvest to your kitchen.
          </p>
        </div>

        <div className="flex flex-col gap-4">
          <h4 className="font-display text-sm font-semibold text-foreground">Quick Links</h4>
          <ul className="flex flex-col gap-2.5">
            {quickLinks.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="text-sm text-muted-foreground transition-colors hover:text-primary"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-col gap-4">
          <h4 className="font-display text-sm font-semibold text-foreground">Contact</h4>
          <ul className="flex flex-col gap-3">
            <li className="flex items-start gap-2 text-sm text-muted-foreground">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <span>123 Harvest Lane, Rajgarh, Madhya Pradesh, India</span>
            </li>
            <li className="flex items-center gap-2 text-sm text-muted-foreground">
              <Phone className="h-4 w-4 shrink-0 text-primary" />
              <span>+91 98765 43210</span>
            </li>
            <li className="flex items-center gap-2 text-sm text-muted-foreground">
              <Mail className="h-4 w-4 shrink-0 text-primary" />
              <span>hello@healthyharvest.example</span>
            </li>
          </ul>
        </div>

        <div className="flex flex-col gap-4">
          <h4 className="font-display text-sm font-semibold text-foreground">Follow Us</h4>
          <div className="flex items-center gap-2">
            {socialLinks.map(({ label, href, icon: Icon }) => (
              <Link
                key={label}
                href={href}
                aria-label={label}
                className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card text-foreground/70 transition-colors hover:border-primary hover:text-primary"
              >
                <Icon className="h-4 w-4" />
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="border-t border-border">
        <div className="container flex flex-col items-center gap-2 py-5 text-xs text-muted-foreground sm:flex-row sm:justify-between">
          <span>&copy; {new Date().getFullYear()} Pramanika. All rights reserved.</span>
          <span>Built with care for wholesome living.</span>
        </div>
      </div>
    </footer>
  );
}
