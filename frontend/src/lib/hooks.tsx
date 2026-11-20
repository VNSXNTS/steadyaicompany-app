import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

// ---------- carregamento de dados ----------
export function useApi<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    load()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((e: Error) => alive && setState((s) => ({ data: s.data, error: e.message, loading: false })));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

// ---------- rota por hash (#/tarefas?agente=cfo) ----------
function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  return { path: path || "/", params: new URLSearchParams(query) };
}

export function useRoute() {
  const [route, setRoute] = useState(parseHash);
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (to: string) => {
  window.location.hash = to;
};

// ---------- avisos ----------
type Notice = { id: number; kind: "ok" | "erro"; text: string };
const ToastCtx = createContext<(text: string, kind?: Notice["kind"]) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Notice[]>([]);
  const push = useCallback((text: string, kind: Notice["kind"] = "ok") => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, kind, text }]);
    setTimeout(() => setItems((s) => s.filter((i) => i.id !== id)), kind === "erro" ? 8000 : 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="fixed bottom-4 right-4 left-4 sm:left-auto z-50 grid gap-2 sm:w-96">
        {items.map((i) => (
          <div
            key={i.id}
            role={i.kind === "erro" ? "alert" : "status"}
            className="rounded-md border px-4 py-3 text-sm bg-raised"
            style={{ borderColor: i.kind === "erro" ? "var(--color-down)" : "var(--color-line)" }}
          >
            {i.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
