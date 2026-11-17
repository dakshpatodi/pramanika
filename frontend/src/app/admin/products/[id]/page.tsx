"use client";

import { useParams } from "next/navigation";

import { ProductEditor } from "@/components/admin/catalog/ProductEditor";

export default function EditProductPage() {
  const { id } = useParams<{ id: string }>();
  return <ProductEditor id={id} />;
}
