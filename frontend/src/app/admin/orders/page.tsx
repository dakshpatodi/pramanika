import { OrdersList } from "@/components/admin/orders/OrdersList";
import { isOrderStatusFilter } from "@/lib/admin-orders";

/** `/admin/orders?status=pending|confirmed|...` opens the list pre-filtered (the overview's status counts link here). */
export default async function AdminOrdersPage({ searchParams }: { searchParams: Promise<{ status?: string | string[] }> }) {
  const { status } = await searchParams;
  return <OrdersList initialStatus={isOrderStatusFilter(status) ? status : undefined} />;
}
