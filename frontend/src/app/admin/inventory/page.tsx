import { InventoryList } from "@/components/admin/inventory/InventoryList";
import { isStockFilter } from "@/lib/admin-inventory-form";

/** `/admin/inventory?stock=low|out|ok` opens the list pre-filtered (the overview's stock alerts link here). */
export default async function AdminInventoryPage({ searchParams }: { searchParams: Promise<{ stock?: string | string[] }> }) {
  const { stock } = await searchParams;
  return <InventoryList initialStock={isStockFilter(stock) ? stock : undefined} />;
}
