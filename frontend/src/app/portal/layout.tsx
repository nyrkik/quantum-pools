/**
 * Customer-facing portal layout. Distinct from the staff (dashboard) layout —
 * no sidebar, no nav, no admin chrome. Customers see only their own surface,
 * branded by the org they belong to.
 */
export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-muted/30 text-foreground">{children}</div>
  );
}
