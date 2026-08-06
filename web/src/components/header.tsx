"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { api, type Health } from "@/lib/api";

export function Header() {
  const { theme, setTheme } = useTheme();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
        <Link href="/" className="flex items-baseline gap-2">
          <span className="text-sm font-semibold tracking-tight">
            blog-gen
          </span>
          <span className="text-xs text-muted-foreground">
            humanizer pipeline
          </span>
        </Link>
        <div className="flex items-center gap-3">
          <span className="hidden rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground sm:inline-flex">
            mode: {health?.mode ?? "…"}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Toggle theme"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            <Sun className="size-4 hidden dark:block" />
            <Moon className="size-4 dark:hidden" />
          </Button>
        </div>
      </div>
    </header>
  );
}
