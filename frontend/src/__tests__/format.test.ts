import { describe, expect, it } from "vitest";
import { percent, toCents, usd } from "../lib/format";

describe("format", () => {
  it("converte centavos em dólares", () => {
    expect(usd(1990).replace(/\s/g, " ")).toContain("19,90");
  });
  it("percentual nulo vira traço, nunca zero", () => {
    expect(percent(null)).toBe("—");
    expect(percent(12.5)).toContain("12,5");
  });
  it("toCents aceita vírgula e ponto e rejeita lixo", () => {
    expect(toCents("12,50")).toBe(1250);
    expect(toCents("12.5")).toBe(1250);
    expect(toCents("1.234,56")).toBe(123456);
    expect(toCents("abc")).toBeNull();
    expect(toCents("-3")).toBeNull();
    expect(toCents("1,234")).toBeNull();
  });
});
