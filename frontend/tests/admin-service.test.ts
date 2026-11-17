import { beforeEach, describe, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/axios", () => ({ apiClient: { get } }));

import { getAdminDashboard, getAdminMe } from "@/services/admin";
import { dashboard } from "./admin-fixtures";

beforeEach(() => {
  get.mockReset();
});

describe("admin service", () => {
  it("getAdminMe asks the server who the caller is and unwraps the envelope", async () => {
    const me = { id: "u1", email: "a@x.com", first_name: "A", last_name: "B", role: "admin" };
    get.mockResolvedValue({ data: { success: true, message: "OK", data: me } });
    await expect(getAdminMe()).resolves.toEqual(me);
    expect(get).toHaveBeenCalledWith("/api/admin/me");
  });

  it("getAdminDashboard reads /api/admin/dashboard", async () => {
    const data = dashboard();
    get.mockResolvedValue({ data: { success: true, message: "OK", data } });
    await expect(getAdminDashboard()).resolves.toEqual(data);
    expect(get).toHaveBeenCalledWith("/api/admin/dashboard");
  });

  it("lets a failure reach the caller (so the screen can show it)", async () => {
    get.mockRejectedValue(new Error("boom"));
    const outcome = await getAdminDashboard().then(
      () => "resolved",
      (error: Error) => error.message
    );
    expect(outcome).toBe("boom");
  });
});
