import { useSyncExternalStore } from "react";

/** Minimal hash router: two top-level views don't justify a routing dependency. */
export type Route = "dashboard" | "import";

const ROUTES: Record<string, Route> = { "": "dashboard", "#/": "dashboard", "#/import": "import" };

function current(): Route {
  return ROUTES[window.location.hash] ?? "dashboard";
}

function subscribe(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export const useRoute = () => useSyncExternalStore(subscribe, current, () => "dashboard" as Route);

export const hrefFor = (route: Route) => (route === "dashboard" ? "#/" : `#/${route}`);
