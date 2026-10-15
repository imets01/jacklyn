import { lazy, Suspense } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { Skeleton } from "@/components/ui/primitives";
import { PreferencesProvider } from "@/lib/preferences";
import { useRoute } from "@/lib/router";

const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const ImporterPage = lazy(() =>
  import("@/pages/ImporterPage").then((m) => ({ default: m.ImporterPage })),
);

export default function App() {
  const route = useRoute();
  return (
    <PreferencesProvider>
      <AppShell route={route}>
        <Suspense fallback={<Skeleton className="h-96" />}>
          {route === "import" ? <ImporterPage /> : <DashboardPage />}
        </Suspense>
      </AppShell>
    </PreferencesProvider>
  );
}
