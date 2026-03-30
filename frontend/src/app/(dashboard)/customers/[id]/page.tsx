"use client";

import { use } from "react";
import { CustomerDetailContent } from "@/components/customers/customer-detail-content";

export default function CustomerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <CustomerDetailContent id={id} />;
}
