import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Em desenvolvimento, as chamadas à API passam por este proxy (backend em :8000).
// A navegação do painel usa #/rotas, então não conflita com os caminhos da API.
const target = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";
const apiPaths =
  "^/(agents|agents-stats|tasks|ceo|approvals|products|sales|expenses|dashboard|costs|providers|settings|health)(/|$)";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { [apiPaths]: target } },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"] },
});
