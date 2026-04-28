import { redirect } from "next/navigation";

export default function ReconciliationRedirect() {
  redirect("/invoices?tab=reconciliation");
}
