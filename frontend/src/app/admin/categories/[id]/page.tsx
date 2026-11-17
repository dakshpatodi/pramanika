"use client";

import { useParams } from "next/navigation";

import { CategoryEditor } from "@/components/admin/catalog/CategoryEditor";

export default function EditCategoryPage() {
  const { id } = useParams<{ id: string }>();
  return <CategoryEditor id={id} />;
}
