import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, describeDetail, request } from "../lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("envia X-API-Key", async () => {
    const f = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", f);
    await request("/x", {}, "abc");
    expect(f.mock.calls[0][1].headers["X-API-Key"]).toBe("abc");
  });
  it("401 dispara evento de logout e lança ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Chave inválida" }), { status: 401 })));
    const h = vi.fn();
    window.addEventListener("steady:unauthorized", h);
    await expect(request("/x", {}, "k")).rejects.toMatchObject({ status: 401, message: "Chave inválida" });
    expect(h).toHaveBeenCalled();
    window.removeEventListener("steady:unauthorized", h);
  });
  it("servidor fora do ar vira mensagem legível", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    await expect(request("/x", {}, "k")).rejects.toBeInstanceOf(ApiError);
  });
  it("detalhe 422 é legível", () => {
    expect(describeDetail([{ loc: ["body", "description"], msg: "muito curto" }])).toBe("description: muito curto");
  });
});
