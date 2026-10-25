import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { invoiceFileName, saveBlob } from "@/lib/download";

describe("invoiceFileName", () => {
  it("is named after the order number", () => {
    expect(invoiceFileName("PRM-2026-000042", "id")).toBe("invoice-PRM-2026-000042.pdf");
  });
  it("replaces anything that could be a path or header trick", () => {
    const name = invoiceFileName('../../x";\r\nSet-Cookie: a=b', "id");
    expect(name).toMatch(/^invoice-[A-Za-z0-9._-]+\.pdf$/);
    expect(name).not.toContain("/");
  });
  it("falls back to the start of the order id when there is no number", () => {
    expect(invoiceFileName(null, "0123456789abcdef")).toBe("invoice-0123456789ab.pdf");
  });
});

describe("saveBlob", () => {
  const created: string[] = [];
  const revoked: string[] = [];
  let clicked: HTMLAnchorElement[] = [];

  beforeEach(() => {
    created.length = 0; revoked.length = 0; clicked = [];
    vi.stubGlobal("URL", Object.assign(URL, {
      createObjectURL: vi.fn((b: Blob) => { const u = `blob:test/${created.length}`; created.push(u); void b; return u; }),
      revokeObjectURL: vi.fn((u: string) => { revoked.push(u); }),
    }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { clicked.push(this); });
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("clicks a download link for the blob with the given name, then removes the link", async () => {
    saveBlob(new Blob(["%PDF"]), "invoice-1.pdf");
    expect(clicked).toHaveLength(1);
    expect(clicked[0].getAttribute("download")).toBe("invoice-1.pdf");
    expect(clicked[0].getAttribute("href")).toBe("blob:test/0");
    expect(document.body.contains(clicked[0])).toBe(false);
    await new Promise((r) => setTimeout(r, 5)); // let the deferred revoke run before the next test
  });

  it("releases the temporary URL afterwards, not before the click", async () => {
    saveBlob(new Blob(["%PDF"]), "invoice-1.pdf");
    expect(revoked).toEqual([]);
    await new Promise((r) => setTimeout(r, 5));
    expect(revoked).toEqual(["blob:test/0"]);
  });
});
