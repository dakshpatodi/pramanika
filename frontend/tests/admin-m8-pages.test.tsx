import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/admin/inventory/InventoryList", () => ({ InventoryList: () => null }));
vi.mock("@/components/admin/orders/OrdersList", () => ({ OrdersList: () => null }));

import AdminInventoryPage from "@/app/admin/inventory/page";
import AdminOrdersPage from "@/app/admin/orders/page";

const stockProp = async (stock: string | string[] | undefined) =>
  ((await AdminInventoryPage({ searchParams: Promise.resolve({ stock }) })) as { props: { initialStock?: string } }).props.initialStock;
const statusProp = async (status: string | string[] | undefined) =>
  ((await AdminOrdersPage({ searchParams: Promise.resolve({ status }) })) as { props: { initialStatus?: string } }).props.initialStatus;

describe("admin list pages read a pre-filter from the address", () => {
  it("inventory accepts ok / low / out and nothing else", async () => {
    for (const ok of ["ok", "low", "out"]) expect(await stockProp(ok)).toBe(ok);
    for (const bad of [undefined, "", "all", "LOW", "low; drop table", ["low", "out"]]) expect(await stockProp(bad)).toBeUndefined();
  });
  it("orders accepts the seven statuses and nothing else", async () => {
    for (const ok of ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded"]) expect(await statusProp(ok)).toBe(ok);
    for (const bad of [undefined, "", "paid", "SHIPPED", "<script>", ["pending", "shipped"]]) expect(await statusProp(bad)).toBeUndefined();
  });
});
