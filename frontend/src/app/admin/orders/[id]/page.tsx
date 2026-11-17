"use client";

import { useParams } from "next/navigation";

import { OrderDetail } from "@/components/admin/orders/OrderDetail";

export default function AdminOrderPage() {
  const { id } = useParams<{ id: string }>();
  return <OrderDetail id={id} />;
}
