import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { BASE_CURRENCIES, type BaseCurrency } from "./types";

type Theme = "light" | "dark";

interface Preferences {
  theme: Theme;
  toggleTheme: () => void;
  baseCurrency: BaseCurrency;
  setBaseCurrency: (c: BaseCurrency) => void;
}

const PreferencesContext = createContext<Preferences | null>(null);

const THEME_KEY = "jacklyn.theme";
const CURRENCY_KEY = "jacklyn.baseCurrency";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode / storage blocked: preference just won't persist */
  }
}

function initialTheme(): Theme {
  const saved = read(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function initialCurrency(): BaseCurrency {
  const saved = read(CURRENCY_KEY);
  return (BASE_CURRENCIES as readonly string[]).includes(saved ?? "")
    ? (saved as BaseCurrency)
    : "CHF";
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [baseCurrency, setCurrency] = useState<BaseCurrency>(initialCurrency);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", theme === "dark" ? "#0c1410" : "#f6f7f2");
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      write(THEME_KEY, next);
      return next;
    });
  }, []);

  const setBaseCurrency = useCallback((c: BaseCurrency) => {
    write(CURRENCY_KEY, c);
    setCurrency(c);
  }, []);

  const value = useMemo(
    () => ({ theme, toggleTheme, baseCurrency, setBaseCurrency }),
    [theme, toggleTheme, baseCurrency, setBaseCurrency],
  );
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): Preferences {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error("usePreferences must be used inside <PreferencesProvider>");
  return ctx;
}
