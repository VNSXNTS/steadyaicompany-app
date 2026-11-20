import type { ReactNode } from "react";

export function PageHeader({ title, intro, actions }: { title: string; intro?: string; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 pb-6">
      <div className="max-w-2xl">
        <h1 className="display text-[2.1rem] leading-tight font-medium m-0">{title}</h1>
        {intro && <p className="text-muted mt-1 mb-0">{intro}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Section({ title, note, children, actions }: { title: string; note?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="py-6 border-t border-line">
      <div className="flex flex-wrap items-baseline justify-between gap-3 mb-4">
        <div>
          <h2 className="display text-xl font-medium m-0">{title}</h2>
          {note && <p className="text-muted text-sm mt-1 mb-0 max-w-2xl">{note}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

const dotColor: Record<string, string> = {
  active: "var(--color-up)", completed: "var(--color-up)", published: "var(--color-up)", approved: "var(--color-up)",
  running: "var(--color-brass)", in_review: "var(--color-brass)",
  pending: "var(--color-muted)", draft: "var(--color-muted)", paused: "var(--color-warn)",
  awaiting_approval: "var(--color-warn)", failed: "var(--color-down)", cancelled: "var(--color-muted)",
  rejected: "var(--color-down)", changes_requested: "var(--color-warn)",
};

/** Estado com bolinha de cor e sempre com texto: a cor nunca é a única informação. */
export function Status({ value, label }: { value: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: dotColor[value] ?? "var(--color-muted)" }} />
      {label}
    </span>
  );
}

export function Loading({ what = "dados" }: { what?: string }) {
  return <p className="text-muted">Carregando {what}…</p>;
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="border-l-2 pl-4 py-1" style={{ borderColor: "var(--color-down)" }}>
      <p className="m-0">{message}</p>
      {onRetry && (
        <button className="btn btn-small mt-3" onClick={onRetry}>
          Tentar de novo
        </button>
      )}
    </div>
  );
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="py-8">
      <p className="display text-lg m-0">{title}</p>
      {hint && <p className="text-muted mt-1 mb-0 max-w-xl">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      {label}
      {children}
    </label>
  );
}
