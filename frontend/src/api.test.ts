import { describe, it, expect, vi, afterEach } from "vitest";
import { api, percent, when } from "./api";
describe("honest display", () => {
  it("does not turn missing rates into success", () => {
    expect(percent(null)).toBe("—");
    expect(percent(0)).toBe("0.0%");
    expect(when(null)).toBe("Never checked");
  });
});
describe("API boundary", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("sends CSRF cookie on writes", async () => {
    document.cookie = "csrf=token";
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    vi.stubGlobal("fetch", fetcher);
    await api("/settings", { method: "PUT", body: "{}" });
    expect(fetcher.mock.calls[0][1].headers["X-CSRF-Token"]).toBe("token");
  });
  it("rejects authorization errors instead of rendering false success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: () =>
          Promise.resolve({ detail: "Administrator access required" }),
      }),
    );
    await expect(api("/settings")).rejects.toThrow(
      "Administrator access required",
    );
  });
});
