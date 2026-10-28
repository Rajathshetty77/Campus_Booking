import AppShell from "@/components/AppShell";

// The signed-in area waits for the session check in the browser before rendering,
// so navigations into it are allowed to block.
export const instant = false;

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
