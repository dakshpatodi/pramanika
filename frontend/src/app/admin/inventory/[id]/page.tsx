"use client";

import { useParams } from "next/navigation";

import { InventoryEditor } from "@/components/admin/inventory/InventoryEditor";

export default function AdminInventoryItemPage() {
  const { id } = useParams<{ id: string }>();
  return <InventoryEditor id={id} />;
}
