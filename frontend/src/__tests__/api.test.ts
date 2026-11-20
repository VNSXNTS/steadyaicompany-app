import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, describeDetail, request } from "../lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("envia cookies da sessão sem enviar chave de API", async () => {
    const f = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", f);
    await request("/x");
    expect(f.mock.calls[0][1].credentials).toBe("same-origin");
    expect(f.mock.calls[0][1].headers["X-API-Key"]).toBeUndefined();
  });
  it("401 dispara evento de logout e lança ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Sessão inválida" }), { status: 401 })));
    const h = vi.fn();
    window.addEventListener("steady:unauthorized", h);
    await expect(request("/x")).rejects.toMatchObject({ status: 401, message: "Sessão inválida" });
    expect(h).toHaveBeenCalled();
    window.removeEventListener("steady:unauthorized", h);
  });
  it("servidor fora do ar vira mensagem legível", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    await expect(request("/x")).rejects.toBeInstanceOf(ApiError);
  });
  it("detalhe 422 é legível", () => {
    expect(describeDetail([{ loc: ["body", "description"], msg: "muito curto" }])).toBe("description: muito curto");
  });
});
