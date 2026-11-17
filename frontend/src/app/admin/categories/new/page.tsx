import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { CategoryForm } from "@/components/admin/catalog/CategoryForm";

export default function NewCategoryPage() {
  return (
    <>
      <AdminPageHeader title="New category" description="Categories group products in the shop." />
      <CategoryForm />
    </>
  );
}
