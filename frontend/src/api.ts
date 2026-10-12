export type State =
  | "Healthy"
  | "Warning"
  | "Critical"
  | "Unknown"
  | "Never Checked"
  | "Not Configured";
export interface Card {
  category: string;
  state: State;
  summary: string;
  checked_at: string | null;
  evidence: Record<string, unknown>;
}
export interface Overview {
  score: number | null;
  coverage: number;
  penalty: number;
  provisional: boolean;
  state: string;
  summary: string;
  cards: Card[];
  delivery: {
    total: number;
    delivery_rate: number | null;
    bounce_rate: number | null;
    hard_bounce_rate: number | null;
    soft_bounce_rate: number | null;
    failure_rate: number | null;
    spf_alignment_rate: number | null;
    dkim_alignment_rate: number | null;
  };
  issues: { open: number; critical: number; verified: number };
  placements: {
    id: number;
    provider: string;
    state: string;
    created_at: string;
    detail: string;
  }[];
  factors: {
    category: string;
    weight: number;
    earned: number | null;
    state: string;
  }[];
}
export interface Issue {
  id: number;
  title: string;
  category: string;
  severity: string;
  status: string;
  technical: string;
  meaning: string;
  action: string;
  impact: string;
  owner: string | null;
  detected_at: string;
  last_seen: string;
  verified_by: string | null;
  verified_at: string | null;
  retest_result: string | null;
  evidence: Record<string, unknown>;
}
export interface Series {
  time: string;
  health: number | null;
  delivery_rate: number | null;
  bounce_rate: number | null;
  authentication: number | null;
  inbox: number;
  spam: number;
  reputation: number | null;
  failures: number;
  issues: number;
}
export interface Domain {
  id: number;
  name: string;
  selectors: string[];
}
export interface Monitoring {
  intervals: Record<string, number>;
  bounce_threshold: number;
  failure_threshold: number;
  alert_cooldown: number;
  health_healthy: number;
  health_excellent: number;
}
export interface Settings {
  monitoring: Monitoring;
  domain: Domain;
  sending_ips: string[];
  seeds: {
    id: number;
    provider: string;
    email: string;
    imap_host: string;
    active: boolean;
  }[];
  integrations: Record<string, boolean>;
  demo_mode: boolean;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const csrf =
    document.cookie
      .split("; ")
      .find((v) => v.startsWith("csrf="))
      ?.split("=")[1] || "";
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      ...options.headers,
    },
    credentials: "same-origin",
  });
  if (!response.ok) {
    let message = "Request failed";
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : "Please check the entered values.";
    } catch {}
    if (response.status === 401) window.dispatchEvent(new Event("signed-out"));
    throw new Error(message);
  }
  return response.json();
}
export function percent(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(1) + "%";
}
export function when(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "Never checked";
}
