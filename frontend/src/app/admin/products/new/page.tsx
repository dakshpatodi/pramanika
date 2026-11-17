import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ProductForm } from "@/components/admin/catalog/ProductForm";

export default function NewProductPage() {
  return (
    <>
      <AdminPageHeader title="New product" description="Creating a product also sets its opening stock." />
      <ProductForm />
    </>
  );
}
