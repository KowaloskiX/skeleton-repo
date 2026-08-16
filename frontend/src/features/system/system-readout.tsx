import { useQuery } from "@tanstack/react-query";
import type { CSSProperties, ReactNode } from "react";

import { Panel, PanelHeader } from "@/components/ui/panel";
import { useSession } from "@/features/auth";
import { healthGetOptions } from "@/lib/api";

type RowState = "live" | "pending";

type Row = {
  label: string;
  value: string;
  state: RowState;
};

/** Layers not built yet — deliberately visible so the readout does not lie. */
const PLANNED: readonly Row[] = [
  { label: "observability (otel)", value: "increment 8", state: "pending" },
  { label: "ai ports + vectors", value: "increment 9", state: "pending" },
];

const WIRED: readonly Row[] = [
  { label: "mongodb + atlas search", value: "replica set", state: "live" },
  { label: "rate limit", value: "shared on redis", state: "live" },
  { label: "argon2id passwords", value: "pwdlib", state: "live" },
  { label: "server-side sessions", value: "httponly cookie", state: "live" },
  { label: "csrf", value: "signed double-submit", state: "live" },
  { label: "api client", value: "openapi → ts", state: "live" },
  { label: "layer boundaries", value: "enforced in CI", state: "live" },
];

function StatusGlyph({ state }: { state: RowState }): ReactNode {
  return (
    <span aria-hidden className={state === "live" ? "text-live" : "text-muted/60"}>
      {state === "live" ? "●" : "○"}
    </span>
  );
}

function ReadoutRow({ row, index }: { row: Row; index: number }): ReactNode {
  return (
    <li
      className="readout-row flex items-baseline gap-2.5 px-4 py-1.5 font-mono text-xs"
      style={{ "--row-index": index } as CSSProperties}
    >
      <StatusGlyph state={row.state} />
      <span className="whitespace-nowrap text-ink">{row.label}</span>
      {/* Dotted leader: never wraps, gives the remaining width to the value. */}
      <span className="min-w-3 flex-1 border-b border-dashed border-line" aria-hidden />
      <span
        className={`truncate whitespace-nowrap ${row.state === "live" ? "text-muted" : "text-muted/70"}`}
      >
        {row.value}
      </span>
      <span className="sr-only">{row.state === "live" ? "ready" : "planned"}</span>
    </li>
  );
}

/**
 * The signature element of the page: not a promise, but a status readout. The first two rows
 * come from real API calls; the rest describe what is wired up and what is merely planned.
 */
export function SystemReadout(): ReactNode {
  const health = useQuery(healthGetOptions());
  const { user, isKnown: sessionKnown } = useSession();

  const healthValue = health.data
    ? `${health.data.status} · ${health.data.env}`
    : health.isPending
      ? "checking…"
      : "no response";

  const liveRows: Row[] = [
    {
      label: "api /api/health",
      value: healthValue,
      state: health.data ? "live" : "pending",
    },
    {
      label: "session",
      value: !sessionKnown ? "checking…" : user ? user.email : "signed out",
      state: user ? "live" : "pending",
    },
  ];

  const rows = [...liveRows, ...WIRED, ...PLANNED];

  return (
    <Panel>
      <PanelHeader>
        <span>system readout</span>
        <span>
          {rows.filter((row) => row.state === "live").length}/{rows.length} ready
        </span>
      </PanelHeader>
      <ul className="py-2">
        {rows.map((row, index) => (
          <ReadoutRow key={row.label} row={row} index={index} />
        ))}
      </ul>
    </Panel>
  );
}
