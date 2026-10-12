import React, { useEffect, useState, FormEvent } from "react";
import { createRoot } from "react-dom/client";
import {
  LayoutDashboard,
  ShieldCheck,
  Send,
  Inbox,
  Globe,
  AlertCircle,
  FileText,
  History,
  Settings as SettingsIcon,
  Activity,
  ChevronRight,
  ArrowUpRight,
  RefreshCw,
  Check,
  LogOut,
  Menu,
  X,
  Search,
  CheckCircle2,
  Clock,
  Mail,
  ExternalLink,
  Download,
  LockKeyhole,
  Radio,
  ArrowRight,
  Info,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  LineChart,
  Line,
  Legend,
} from "recharts";
import {
  api,
  percent,
  when,
  Overview,
  Card,
  Issue,
  Series,
  Domain,
  Settings,
  Monitoring,
} from "./api";
import "./style.css";
const navigation = [
  ["Overview", LayoutDashboard],
  ["Authentication", ShieldCheck],
  ["Deliverability", Send],
  ["Inbox Placement", Inbox],
  ["Reputation", Globe],
  ["Issues", AlertCircle],
  ["Reports", FileText],
  ["Monitoring History", History],
  ["Settings", SettingsIcon],
  ["System Status", Activity],
] as const;
function Brand() {
  const [missing, setMissing] = useState(!import.meta.env.VITE_LOGO_AVAILABLE);
  return (
    <div className="brand">
      {!missing && (
        <img
          src="/branding/newhotmusic-logo.png"
          alt="NewHotMusic official logo"
          onError={() => setMissing(true)}
        />
      )}
      <div>
        <strong>
          NewHotMusic<span>.com</span>
        </strong>
        <small>EMAIL HEALTH</small>
      </div>
    </div>
  );
}
export function Badge({ state }: { state: string }) {
  const tone = [
    "Healthy",
    "Excellent",
    "Operational",
    "Inbox",
    "Verified",
    "Closed",
    "Sent",
    "Configured",
  ].includes(state)
    ? "good"
    : ["Critical", "Unavailable", "Spam", "Failed"].includes(state)
      ? "bad"
      : ["Warning", "Needs Attention", "Degraded", "Missing"].includes(state)
        ? "warn"
        : "neutral";
  return (
    <span className={"badge " + tone}>
      <i />
      {state}
    </span>
  );
}
function Empty({
  title = "No measurements yet",
  text = "Once monitoring runs, real results will appear here.",
}: {
  title?: string;
  text?: string;
}) {
  return (
    <div className="empty">
      <Activity size={28} />
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}
function Login({ onLogin }: { onLogin: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(data)),
      });
      onLogin();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login">
      <section className="login-story">
        <Brand />
        <div className="story-body">
          <span className="eyebrow">EVERY MESSAGE MATTERS</span>
          <h1>
            Good music.
            <br />
            Great connections.
          </h1>
          <p>
            Keep your audience close. See the health of every email connection,
            all in one place.
          </p>
          <div className="story-line">
            <span />
            <span />
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        </div>
        <small>NewHotMusic · Email intelligence, made clear.</small>
      </section>
      <main className="login-form">
        <div>
          <div className="login-icon">
            <LockKeyhole />
          </div>
          <span className="eyebrow">YOUR EMAIL HEALTH, AT A GLANCE</span>
          <h2>Welcome back.</h2>
          <p>Sign in to your NewHotMusic monitoring workspace.</p>
          <form onSubmit={submit}>
            <label>
              Email address
              <input
                name="email"
                type="email"
                autoComplete="username"
                required
                placeholder="you@newhotmusic.com"
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            {error && (
              <p role="alert" className="form-error">
                {error}
              </p>
            )}
            <button className="primary" disabled={busy}>
              {busy ? "Signing in…" : "Sign in to dashboard"}
              <ArrowRight size={18} />
            </button>
          </form>
          <small className="security-note">
            <ShieldCheck size={14} /> Secure access · Authorized team members
            only
          </small>
        </div>
      </main>
    </div>
  );
}
function Chart({
  series,
  title,
  keys,
  unit = "%",
}: {
  series: Series[];
  title: string;
  keys: { key: keyof Series; label: string; color: string }[];
  unit?: string;
}) {
  const hasData = series.some((p) =>
    keys.some((k) => p[k.key] != null && typeof p[k.key] === "number"),
  );
  return (
    <section className="panel chart-panel">
      <div className="panel-head">
        <h3>{title}</h3>
        <span className="subtle">Measured history</span>
      </div>
      {!hasData ? (
        <Empty />
      ) : (
        <ResponsiveContainer width="100%" height={230}>
          <AreaChart
            data={series}
            margin={{ top: 12, right: 16, bottom: 0, left: -15 }}
          >
            <defs>
              {keys.map((k) => (
                <linearGradient
                  key={k.key}
                  id={"fill-" + k.key}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="0%" stopColor={k.color} stopOpacity={0.2} />
                  <stop offset="100%" stopColor={k.color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid
              strokeDasharray="3 5"
              vertical={false}
              stroke="#e9eeea"
            />
            <XAxis
              dataKey="time"
              tickFormatter={(v) =>
                new Date(v).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                })
              }
              tick={{ fontSize: 11, fill: "#89918a" }}
              axisLine={false}
              tickLine={false}
              minTickGap={40}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#89918a" }}
              axisLine={false}
              tickLine={false}
              domain={unit === "%" ? [0, 100] : ["auto", "auto"]}
            />
            <Tooltip
              labelFormatter={(v) => when(String(v))}
              formatter={(v) => (v == null ? "Unknown" : String(v) + unit)}
              contentStyle={{
                borderRadius: 12,
                border: "1px solid #e6ebe6",
                fontSize: 12,
              }}
            />
            <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
            {keys.map((k) => (
              <Area
                key={k.key}
                name={k.label}
                dataKey={k.key}
                type="monotone"
                stroke={k.color}
                strokeWidth={2.5}
                fill={"url(#fill-" + k.key + ")"}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      )}
    </section>
  );
}
function CheckCard({ card, onClick }: { card: Card; onClick: () => void }) {
  return (
    <button className="check-card" onClick={onClick}>
      <div>
        <span className="check-icon">
          {card.state === "Healthy" ? (
            <Check size={16} />
          ) : card.state === "Critical" ? (
            <AlertCircle size={16} />
          ) : (
            <ShieldCheck size={16} />
          )}
        </span>
        <ArrowUpRight size={15} className="subtle" />
      </div>
      <h3>{card.category}</h3>
      <Badge state={card.state} />
      <small>
        {card.checked_at
          ? "Checked " + new Date(card.checked_at).toLocaleDateString()
          : "Awaiting first check"}
      </small>
    </button>
  );
}
function Score({
  overview,
  onClick,
}: {
  overview: Overview;
  onClick: () => void;
}) {
  return (
    <section className="health-hero">
      <div className="health-copy">
        <span className="eyebrow">
          <Radio size={13} /> THE BIG PICTURE
        </span>
        <h2>
          {overview.score === null
            ? "Let’s check your email health."
            : overview.state === "Critical"
              ? "Your email needs attention."
              : overview.state === "Needs Attention"
                ? "A few signals need attention."
                : "Your email is in good hands."}
        </h2>
        <p>{overview.summary}</p>
        <div className="hero-tags">
          <Badge state={overview.state} />
          <span>{overview.coverage}% of signals measured</span>
        </div>
        <button onClick={onClick} className="text-button">
          Understand your score <ArrowRight size={15} />
        </button>
      </div>
      <button
        className="score-ring"
        onClick={onClick}
        aria-label="Explain health score"
      >
        <svg viewBox="0 0 160 160">
          <circle
            cx="80"
            cy="80"
            r="66"
            stroke="#e0e8df"
            strokeWidth="9"
            fill="none"
          />
          <circle
            cx="80"
            cy="80"
            r="66"
            stroke={
              overview.score !== null && overview.score < 50
                ? "#e26d55"
                : "#476f3a"
            }
            strokeWidth="9"
            fill="none"
            strokeLinecap="round"
            strokeDasharray={`${(overview.score || 0) * 4.147} 415`}
            transform="rotate(-90 80 80)"
          />
        </svg>
        <div>
          <strong>{overview.score ?? "—"}</strong>
          <small>
            {overview.provisional ? "PROVISIONAL SCORE" : "EMAIL HEALTH SCORE"}
          </small>
          <span>out of 100</span>
        </div>
      </button>
    </section>
  );
}
function App() {
  const [auth, setAuth] = useState<boolean | null>(null);
  const [user, setUser] = useState<{
    email: string;
    role: string;
    demo_mode?: boolean;
  } | null>(null);
  const [page, setPage] = useState("Overview");
  const [mobile, setMobile] = useState(false);
  const [days, setDays] = useState(7);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [domain, setDomain] = useState(0);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [series, setSeries] = useState<Series[]>([]);
  const [checks, setChecks] = useState<Card[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [activity, setActivity] = useState<
    { id: number; action: string; at: string; actor: string }[]
  >([]);
  const [reports, setReports] = useState<
    {
      id: number;
      period: string;
      generated_at: string;
      content: Overview & {
        new_issues: number;
        resolved_issues: number;
        verified_fixes: number;
      };
    }[]
  >([]);
  const [system, setSystem] = useState<{
    services: Record<string, string>;
    last_successful_check: string | null;
    alerts: { id: number; state: string; created_at: string }[];
  } | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [detail, setDetail] = useState<Card | null>(null);
  const [scoreOpen, setScoreOpen] = useState(false);
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [issueHistory, setIssueHistory] = useState<
    { id: number; status: string; actor: string; at: string; note: string }[]
  >([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function session() {
    try {
      setUser(await api("/auth/me"));
      setAuth(true);
      const ds = await api<Domain[]>("/domains");
      setDomains(ds);
      setDomain((d) => d || ds[0]?.id || 0);
    } catch {
      setAuth(false);
    }
  }
  useEffect(() => {
    session();
    const out = () => setAuth(false);
    window.addEventListener("signed-out", out);
    return () => window.removeEventListener("signed-out", out);
  }, []);
  async function load() {
    if (!domain) return;
    try {
      const [o, h, i, a] = await Promise.all([
        api<Overview>(`/overview/${domain}?days=${days}`),
        api<{ series: Series[]; checks: Card[] }>(
          `/history/${domain}?days=${days}`,
        ),
        api<Issue[]>(`/issues/${domain}`),
        api<typeof activity>("/activity"),
      ]);
      setOverview(o);
      setSeries(h.series);
      setChecks(h.checks);
      setIssues(i);
      setActivity(a);
      setError("");
      if (page === "Reports") setReports(await api(`/reports/${domain}`));
      if (page === "System Status") setSystem(await api("/system"));
      if (page === "Settings" && user?.role === "admin")
        setSettings(await api(`/settings/${domain}`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    if (auth && domain) {
      load();
      const timer = setInterval(load, 30000);
      return () => clearInterval(timer);
    }
  }, [auth, domain, days, page]);
  async function action(fn: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    try {
      await fn();
      setNotice(success);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function run(group = "auth") {
    action(
      () => api(`/monitor/${domain}/${group}`, { method: "POST" }),
      "Monitoring queued. Results update automatically as checks complete.",
    );
  }
  async function changeIssue(issue: Issue, status: string) {
    await action(
      () =>
        api(`/issue/${issue.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status, owner: issue.owner || null }),
        }),
      "Issue updated.",
    );
    setSelectedIssue(null);
  }
  function selectIssue(issue: Issue) {
    setSelectedIssue(issue);
    api<typeof issueHistory>(`/issue/${issue.id}/history`)
      .then(setIssueHistory)
      .catch((e) => setError(e.message));
  }
  const currentDomain = domains.find((d) => d.id === domain);
  if (auth === null)
    return <div className="loading">Opening your workspace…</div>;
  if (!auth) return <Login onLogin={session} />;
  const activeIssues = issues.filter((i) => i.status !== "Closed");
  const categories =
    page === "Authentication"
      ? ["SPF", "DKIM", "DMARC", "MX", "PTR"]
      : page === "Deliverability"
        ? ["Delivery Rate", "Bounce Rate", "SMTP", "TLS"]
        : page === "Reputation"
          ? ["Domain Reputation", "IP Reputation", "Blacklist"]
          : ["Inbox Placement"];
  return (
    <div className="app">
      <aside className={mobile ? "sidebar open" : "sidebar"}>
        <Brand />
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav>
          {navigation.map(([name, Icon]) => (
            <button
              key={name}
              className={page === name ? "nav-link active" : "nav-link"}
              onClick={() => {
                setPage(name);
                setMobile(false);
              }}
            >
              <Icon size={18} />
              <span>{name}</span>
              {name === "Issues" && activeIssues.length > 0 && (
                <b>{activeIssues.length}</b>
              )}
              {name === page && <i />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace-status">
            <span />
            <div>
              <strong>NewHotMusic workspace</strong>
              <small>Self-hosted email monitoring</small>
            </div>
          </div>
          <button
            className="profile"
            onClick={() =>
              action(
                () => api("/auth/logout", { method: "POST" }),
                "Signed out",
              )
            }
          >
            <span className="avatar">
              {user?.email.charAt(0).toUpperCase()}
            </span>
            <span>
              <strong>{user?.email.split("@")[0]}</strong>
              <small>
                {user?.role === "admin" ? "Administrator" : "Read-only access"}
              </small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      {mobile && (
        <button
          className="overlay"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <div className="main">
        <header className="topbar">
          <div>
            <button
              className="mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu />
            </button>
            <span className="crumb">
              Workspace <ChevronRight size={13} />
              <strong>{page}</strong>
            </span>
          </div>
          <div className="top-right">
            <span className="private">
              <LockKeyhole size={12} /> Private workspace
            </span>
            <span className="avatar small">
              {user?.email.charAt(0).toUpperCase()}
            </span>
          </div>
        </header>
        <main className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">NEWHOTMUSIC EMAIL HEALTH</div>
              <h1>{page === "Overview" ? "Email overview" : page}</h1>
              <p>
                {page === "Overview"
                  ? "Every signal. Every connection. One clear picture."
                  : `A closer look at ${page.toLowerCase()}, without the guesswork.`}
              </p>
            </div>
            <div className="page-actions">
              <select
                aria-label="Monitored domain"
                value={domain}
                onChange={(e) => setDomain(Number(e.target.value))}
              >
                {domains.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
              {user?.role === "admin" && (
                <button
                  className="primary"
                  disabled={busy || !domain}
                  onClick={() =>
                    run(
                      page === "Deliverability"
                        ? "smtp"
                        : page === "Reputation"
                          ? "reputation"
                          : page === "Inbox Placement"
                            ? "placement"
                            : "auth",
                    )
                  }
                >
                  <RefreshCw size={15} className={busy ? "spin" : ""} /> Run
                  check
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="banner error" role="alert">
              <AlertCircle size={16} />
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="banner" role="status">
              <Info size={16} />
              {notice}
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {user?.demo_mode && (
            <div className="banner">
              DEMO DATA — illustrative samples, not real monitoring results.
              Production mode excludes all demo records.
            </div>
          )}
          {!domain ? (
            <Empty
              title="Add your first domain"
              text="An administrator can add a domain through the API or first-start configuration."
            />
          ) : !overview ? (
            <Empty title="Loading email health…" />
          ) : (
            <>
              {page === "Overview" && (
                <>
                  <Score
                    overview={overview}
                    onClick={() => setScoreOpen(true)}
                  />
                  <div className="kpi-grid">
                    <div className="kpi">
                      <span className="kpi-icon">
                        <Send size={18} />
                      </span>
                      <span>Delivery success</span>
                      <strong>
                        {percent(overview.delivery.delivery_rate)}
                      </strong>
                      <small>
                        {overview.delivery.total
                          ? `${overview.delivery.total} delivery events in this period`
                          : "Awaiting delivery telemetry"}
                      </small>
                    </div>
                    <div className="kpi">
                      <span className="kpi-icon">
                        <Inbox size={18} />
                      </span>
                      <span>Inbox placement</span>
                      <strong>
                        {overview.cards.find(
                          (c) => c.category === "Inbox Placement",
                        )?.state === "Healthy"
                          ? "Inbox"
                          : "—"}
                      </strong>
                      <small>
                        {overview.placements.length
                          ? "Measured with authorized seed accounts"
                          : "Connect your seed mailboxes"}
                      </small>
                    </div>
                    <div className="kpi">
                      <span className="kpi-icon">
                        <AlertCircle size={18} />
                      </span>
                      <span>Open issues</span>
                      <strong>
                        {overview.issues.open}
                        <em>
                          {overview.issues.critical
                            ? `${overview.issues.critical} critical`
                            : "No critical issues"}
                        </em>
                      </strong>
                      <button
                        className="text-button"
                        onClick={() => setPage("Issues")}
                      >
                        View issues <ArrowRight size={12} />
                      </button>
                    </div>
                    <div className="kpi">
                      <span className="kpi-icon">
                        <CheckCircle2 size={18} />
                      </span>
                      <span>Verified fixes</span>
                      <strong>{overview.issues.verified}</strong>
                      <small>Retested and ready to close</small>
                    </div>
                  </div>
                  <div className="section-heading">
                    <div>
                      <h2>Your email foundations</h2>
                      <p>The signals behind every successful send.</p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => setPage("Authentication")}
                    >
                      View details <ArrowRight size={14} />
                    </button>
                  </div>
                  <div className="checks-grid">
                    {overview.cards.slice(0, 6).map((c) => (
                      <CheckCard
                        key={c.category}
                        card={c}
                        onClick={() => setDetail(c)}
                      />
                    ))}
                  </div>
                  <div className="section-heading">
                    <h2>Performance over time</h2>
                    <Range days={days} setDays={setDays} />
                  </div>
                  <div className="charts-grid">
                    <Chart
                      series={series}
                      title="Email health trend"
                      keys={[
                        {
                          key: "health",
                          label: "Email health",
                          color: "#567942",
                        },
                      ]}
                      unit=""
                    />
                    <Chart
                      series={series}
                      title="Delivery & bounce rate"
                      keys={[
                        {
                          key: "delivery_rate",
                          label: "Delivered",
                          color: "#567942",
                        },
                        {
                          key: "bounce_rate",
                          label: "Bounced",
                          color: "#e59964",
                        },
                      ]}
                    />
                  </div>
                  <div className="bottom-grid">
                    <section className="panel">
                      <div className="panel-head">
                        <h3>What needs your attention</h3>
                        <button
                          className="text-button"
                          onClick={() => setPage("Issues")}
                        >
                          All issues <ArrowUpRight size={14} />
                        </button>
                      </div>
                      {activeIssues.length ? (
                        activeIssues.slice(0, 3).map((i) => (
                          <button
                            className="issue-row"
                            key={i.id}
                            onClick={() => selectIssue(i)}
                          >
                            <span
                              className={
                                "issue-dot " + i.severity.toLowerCase()
                              }
                            >
                              <AlertCircle size={18} />
                            </span>
                            <div>
                              <strong>{i.title}</strong>
                              <small>{i.meaning}</small>
                            </div>
                            <Badge state={i.status} />
                            <ChevronRight size={16} />
                          </button>
                        ))
                      ) : (
                        <Empty
                          title="Nothing flagged yet"
                          text="Detected issues and recommended next steps will appear here."
                        />
                      )}
                    </section>
                    <section className="panel">
                      <div className="panel-head">
                        <h3>Recent activity</h3>
                        <History size={16} className="subtle" />
                      </div>
                      <ActivityFeed items={activity.slice(0, 5)} />
                    </section>
                  </div>
                </>
              )}
              {[
                "Authentication",
                "Deliverability",
                "Reputation",
                "Inbox Placement",
              ].includes(page) && (
                <>
                  <div className="info-strip">
                    <Info size={18} />
                    <p>
                      {page === "Authentication"
                        ? "These checks assess published configuration. Message-level SPF/DKIM authentication and alignment require delivery telemetry."
                        : page === "Reputation"
                          ? "Reputation depends on configured, authorized sources. A clean result applies only to sources actually checked."
                          : page === "Inbox Placement"
                            ? "Placement is measured only in authorized seed mailboxes. It does not guarantee placement for every recipient."
                            : "Delivery statistics reflect signed events received from your sending infrastructure."}
                    </p>
                  </div>
                  <div className="checks-grid wide">
                    {overview.cards
                      .filter((c) => categories.includes(c.category))
                      .map((c) => (
                        <CheckCard
                          key={c.category}
                          card={c}
                          onClick={() => setDetail(c)}
                        />
                      ))}
                  </div>
                  {page === "Authentication" && (
                    <>
                      <div className="kpi-grid">
                        <Metric
                          label="Message SPF alignment"
                          value={percent(overview.delivery.spf_alignment_rate)}
                        />
                        <Metric
                          label="Message DKIM alignment"
                          value={percent(overview.delivery.dkim_alignment_rate)}
                        />
                      </div>
                      <div className="section-heading">
                        <h2>Authentication pass rate</h2>
                        <Range days={days} setDays={setDays} />
                      </div>
                      <Chart
                        series={series}
                        title="Message authentication history"
                        keys={[
                          {
                            key: "authentication",
                            label: "SPF or DKIM pass",
                            color: "#567942",
                          },
                        ]}
                      />
                    </>
                  )}
                  {page === "Deliverability" && (
                    <>
                      <div className="kpi-grid">
                        <Metric
                          label="Delivery rate"
                          value={percent(overview.delivery.delivery_rate)}
                        />
                        <Metric
                          label="Hard bounce"
                          value={percent(overview.delivery.hard_bounce_rate)}
                        />
                        <Metric
                          label="Soft bounce"
                          value={percent(overview.delivery.soft_bounce_rate)}
                        />
                        <Metric
                          label="Failure rate"
                          value={percent(overview.delivery.failure_rate)}
                        />
                      </div>
                      <Range days={days} setDays={setDays} />
                      <div className="charts-grid">
                        <Chart
                          series={series}
                          title="Delivery success"
                          keys={[
                            {
                              key: "delivery_rate",
                              label: "Delivered",
                              color: "#567942",
                            },
                          ]}
                        />
                        <Chart
                          series={series}
                          title="Bounce rate"
                          keys={[
                            {
                              key: "bounce_rate",
                              label: "Bounce rate",
                              color: "#e59964",
                            },
                          ]}
                        />
                        <Chart
                          series={series}
                          title="Email failures"
                          keys={[
                            {
                              key: "failures",
                              label: "Failures",
                              color: "#db725d",
                            },
                          ]}
                          unit=""
                        />
                      </div>
                    </>
                  )}
                  {page === "Reputation" && (
                    <>
                      <div className="section-heading">
                        <h2>Reputation history</h2>
                        <Range days={days} setDays={setDays} />
                      </div>
                      <Chart
                        series={series}
                        title="IP reputation · 100 minus abuse confidence"
                        keys={[
                          {
                            key: "reputation",
                            label: "AbuseIPDB indicator",
                            color: "#567942",
                          },
                        ]}
                        unit=""
                      />
                      {user?.role === "admin" && (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => run("blacklist")}
                        >
                          Retest configured blocklists
                        </button>
                      )}
                    </>
                  )}
                  {page === "Inbox Placement" && (
                    <>
                      <section className="panel">
                        <div className="panel-head">
                          <h3>Seed mailbox tests</h3>
                        </div>
                        {overview.placements.length ? (
                          <div className="table-wrap">
                            <table>
                              <thead>
                                <tr>
                                  <th>Provider</th>
                                  <th>Placement</th>
                                  <th>Tested</th>
                                  <th>Details</th>
                                </tr>
                              </thead>
                              <tbody>
                                {overview.placements.map((p) => (
                                  <tr key={p.id}>
                                    <td>{p.provider}</td>
                                    <td>
                                      <Badge state={p.state} />
                                    </td>
                                    <td>{when(p.created_at)}</td>
                                    <td>{p.detail}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <Empty
                            title="No placement tests yet"
                            text="Add authorized Gmail or Outlook accounts in Settings, then run a placement check."
                          />
                        )}
                      </section>
                      <Chart
                        series={series}
                        title="Inbox vs spam"
                        keys={[
                          { key: "inbox", label: "Inbox", color: "#567942" },
                          { key: "spam", label: "Spam", color: "#db725d" },
                        ]}
                        unit=""
                      />
                    </>
                  )}
                </>
              )}
              {page === "Issues" && (
                <>
                  <div className="kpi-grid">
                    <Metric
                      label="Open issues"
                      value={String(activeIssues.length)}
                    />
                    <Metric
                      label="Critical"
                      value={String(overview.issues.critical)}
                    />
                    <Metric
                      label="Verified fixes"
                      value={String(
                        issues.filter((i) => i.status === "Verified").length,
                      )}
                    />
                    <Metric
                      label="Resolved"
                      value={String(
                        issues.filter((i) => i.status === "Closed").length,
                      )}
                    />
                  </div>
                  <section className="panel">
                    <div className="panel-head">
                      <h3>Issue workspace</h3>
                      <span className="subtle">
                        Fix → Retest → Verify → Close
                      </span>
                    </div>
                    {issues.length ? (
                      issues.map((i) => (
                        <button
                          className="issue-row"
                          key={i.id}
                          onClick={() => selectIssue(i)}
                        >
                          <span className="issue-dot">
                            <AlertCircle size={18} />
                          </span>
                          <div>
                            <small>
                              EH-{String(i.id).padStart(4, "0")} · {i.category}{" "}
                              · {i.severity}
                            </small>
                            <strong>{i.title}</strong>
                            <small>{i.meaning}</small>
                          </div>
                          <Badge state={i.status} />
                          <ChevronRight size={16} />
                        </button>
                      ))
                    ) : (
                      <Empty title="No issues detected" />
                    )}
                  </section>
                  <Chart
                    series={series}
                    title="Issues detected over time"
                    keys={[
                      { key: "issues", label: "New issues", color: "#e59964" },
                    ]}
                    unit=""
                  />
                </>
              )}
              {page === "Monitoring History" && (
                <>
                  <div className="section-heading">
                    <h2>Recorded checks</h2>
                    <Range days={days} setDays={setDays} />
                  </div>
                  <section className="panel">
                    {checks.length ? (
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Check</th>
                              <th>Status</th>
                              <th>Checked at</th>
                              <th>Summary</th>
                            </tr>
                          </thead>
                          <tbody>
                            {checks.map((c, i) => (
                              <tr
                                key={i}
                                onClick={() => setDetail(c)}
                                className="clickable"
                              >
                                <td>{c.category}</td>
                                <td>
                                  <Badge state={c.state} />
                                </td>
                                <td>{when(c.checked_at)}</td>
                                <td>{c.summary}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <Empty />
                    )}
                  </section>
                  <section className="panel">
                    <div className="panel-head">
                      <h3>Activity timeline</h3>
                    </div>
                    <ActivityFeed items={activity} />
                  </section>
                </>
              )}
              {page === "Reports" && (
                <>
                  <div className="info-strip">
                    <FileText size={18} />
                    <p>
                      Daily and weekly summaries are generated by the scheduler
                      using recorded checks and delivery data.
                    </p>
                    {user?.role === "admin" && (
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() => run("reports")}
                      >
                        Generate reports
                      </button>
                    )}
                  </div>
                  {reports.length ? (
                    reports.map((r) => (
                      <section className="panel report" key={r.id}>
                        <div className="panel-head">
                          <div>
                            <span className="eyebrow">
                              {r.period.toUpperCase()} SUMMARY
                            </span>
                            <h3>
                              {new Date(r.generated_at).toLocaleDateString(
                                undefined,
                                {
                                  month: "long",
                                  day: "numeric",
                                  year: "numeric",
                                },
                              )}
                            </h3>
                          </div>
                          <button
                            className="secondary"
                            onClick={() => downloadReport(r)}
                          >
                            <Download size={14} /> Export JSON
                          </button>
                        </div>
                        <p>{r.content.summary}</p>
                        <div className="kpi-grid">
                          <Metric
                            label="Email health"
                            value={
                              r.content.score == null
                                ? "Unknown"
                                : String(r.content.score)
                            }
                          />
                          <Metric
                            label="Delivery rate"
                            value={percent(r.content.delivery.delivery_rate)}
                          />
                          <Metric
                            label="New issues"
                            value={String(r.content.new_issues)}
                          />
                          <Metric
                            label="Resolved issues"
                            value={String(r.content.resolved_issues)}
                          />
                        </div>
                        <div className="report-states">
                          {r.content.cards.map((c) => (
                            <div key={c.category}>
                              <span>{c.category}</span>
                              <Badge state={c.state} />
                            </div>
                          ))}
                        </div>
                      </section>
                    ))
                  ) : (
                    <Empty
                      title="Your first report is on its way"
                      text="Generate a summary or wait for the scheduled reporting cycle."
                    />
                  )}
                </>
              )}
              {page === "Settings" &&
                (user?.role === "admin" ? (
                  settings ? (
                    <SettingsPage
                      key={domain}
                      settings={settings}
                      busy={busy}
                      save={(fn, msg) => action(fn, msg)}
                      domainId={domain}
                    />
                  ) : (
                    <Empty title="Loading settings…" />
                  )
                ) : (
                  <Empty
                    title="Administrator access required"
                    text="Your account has read-only access. Contact your administrator to change monitoring settings."
                  />
                ))}
              {page === "System Status" &&
                (system ? (
                  <>
                    <div className="checks-grid wide">
                      {Object.entries(system.services).map(([name, state]) => (
                        <div className="check-card" key={name}>
                          <Activity size={20} />
                          <h3>{name}</h3>
                          <Badge state={state} />
                        </div>
                      ))}
                    </div>
                    <section className="panel">
                      <div className="panel-head">
                        <h3>Latest successful check</h3>
                        <span>{when(system.last_successful_check)}</span>
                      </div>
                      <h3 className="padded">Alert delivery</h3>
                      {system.alerts.length ? (
                        <div className="table-wrap">
                          <table>
                            <thead>
                              <tr>
                                <th>Alert</th>
                                <th>Status</th>
                                <th>Created</th>
                              </tr>
                            </thead>
                            <tbody>
                              {system.alerts.map((a) => (
                                <tr key={a.id}>
                                  <td>#{a.id}</td>
                                  <td>
                                    <Badge state={a.state} />
                                  </td>
                                  <td>{when(a.created_at)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <Empty title="No alerts queued" />
                      )}
                    </section>
                  </>
                ) : (
                  <Empty title="Checking services…" />
                ))}
            </>
          )}
          <footer>
            <span>NewHotMusic Email Health</span>
            <span>Real signals. Clear decisions.</span>
            <button
              className="text-button"
              onClick={() => setPage("System Status")}
            >
              System status <ArrowUpRight size={12} />
            </button>
          </footer>
        </main>
      </div>
      {detail && (
        <Modal
          title={detail.category + " details"}
          onClose={() => setDetail(null)}
        >
          <Badge state={detail.state} />
          <h3>What this means</h3>
          <p>{detail.summary}</p>
          <p className="subtle">Last checked: {when(detail.checked_at)}</p>
          <details open>
            <summary>Technical evidence</summary>
            <pre>{JSON.stringify(detail.evidence, null, 2)}</pre>
          </details>
        </Modal>
      )}
      {scoreOpen && overview && (
        <Modal
          title="Understanding your health score"
          onClose={() => setScoreOpen(false)}
        >
          <p>{overview.summary}</p>
          <div className="info-strip">
            Measurement coverage: {overview.coverage}%. Critical issue penalty:{" "}
            {overview.penalty} points.
          </div>
          <table>
            <thead>
              <tr>
                <th>Signal</th>
                <th>Weight</th>
                <th>Status</th>
                <th>Earned</th>
              </tr>
            </thead>
            <tbody>
              {overview.factors.map((f) => (
                <tr key={f.category}>
                  <td>{f.category}</td>
                  <td>{f.weight}</td>
                  <td>
                    <Badge state={f.state} />
                  </td>
                  <td>{f.earned ?? "Unmeasured"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Healthy signals earn full weight; warnings earn half; critical
            signals earn zero. The result is normalized across measured signals,
            then reduced by 5 points per active critical issue, up to 20.
            Improve flagged signals and run a retest.
          </p>
        </Modal>
      )}
      {selectedIssue && (
        <Modal
          title={`EH-${String(selectedIssue.id).padStart(4, "0")} · ${selectedIssue.title}`}
          onClose={() => setSelectedIssue(null)}
        >
          <Badge state={selectedIssue.status} />
          <p className="subtle">
            {selectedIssue.severity} · Owner:{" "}
            {selectedIssue.owner || "Unassigned"}
          </p>
          <h3>What this means</h3>
          <p>{selectedIssue.meaning}</p>
          <h3>Business impact</h3>
          <p>{selectedIssue.impact}</p>
          <h3>Recommended action</h3>
          <p>{selectedIssue.action}</p>
          <details>
            <summary>Technical details</summary>
            <p>{selectedIssue.technical}</p>
            <pre>{JSON.stringify(selectedIssue.evidence, null, 2)}</pre>
          </details>
          {selectedIssue.retest_result && (
            <div className="info-strip">
              Retest: {selectedIssue.retest_result}
              <br />
              Verified by: {selectedIssue.verified_by || "Not verified"} ·{" "}
              {when(selectedIssue.verified_at)}
            </div>
          )}
          <h3>Issue timeline</h3>
          {issueHistory.map((h) => (
            <div className="timeline-item" key={h.id}>
              <Badge state={h.status} />
              <small>
                {when(h.at)} · {h.actor}
              </small>
              <p>{h.note}</p>
            </div>
          ))}
          {user?.role === "admin" && (
            <div>
              <label>
                Issue owner
                <input
                  type="email"
                  value={selectedIssue.owner || ""}
                  onChange={(e) =>
                    setSelectedIssue({
                      ...selectedIssue,
                      owner: e.target.value,
                    })
                  }
                  placeholder="owner@newhotmusic.com"
                />
              </label>
              <div className="modal-actions">
                {nextStates(selectedIssue.status).map((s) => (
                  <button
                    className="primary"
                    disabled={busy}
                    key={s}
                    onClick={() => changeIssue(selectedIssue, s)}
                  >
                    {s === "Retesting"
                      ? "Run verification retest"
                      : "Move to " + s}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
function nextStates(state: string): string[] {
  return (
    (
      {
        Open: ["Assigned", "Fixing"],
        Assigned: ["Fixing"],
        Fixing: ["Ready for Retest"],
        "Ready for Retest": ["Retesting"],
        Verified: ["Closed"],
      } as Record<string, string[]>
    )[state] || []
  );
}
function Range({
  days,
  setDays,
}: {
  days: number;
  setDays: (d: number) => void;
}) {
  return (
    <div className="range" aria-label="Time range">
      {[
        [1, "24 hours"],
        [7, "7 days"],
        [30, "30 days"],
        [90, "90 days"],
      ].map(([d, label]) => (
        <button
          key={d}
          className={days === d ? "selected" : ""}
          onClick={() => setDays(Number(d))}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="kpi">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
function ActivityFeed({
  items,
}: {
  items: { id: number; action: string; at: string; actor: string }[];
}) {
  return items.length ? (
    <div className="activity-list">
      {items.map((a) => (
        <div className="activity-item" key={a.id}>
          <span>
            <Check size={12} />
          </span>
          <div>
            <strong>{a.action}</strong>
            <small>{when(a.at)}</small>
          </div>
        </div>
      ))}
    </div>
  ) : (
    <Empty title="Your monitoring timeline starts here" />
  );
}
function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const fn = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", fn);
    const previous = document.activeElement as HTMLElement;
    const close = document.querySelector<HTMLButtonElement>(".modal-close");
    close?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const nodes = Array.from(
        document.querySelectorAll<HTMLElement>(
          ".modal button,.modal input,.modal select,.modal summary",
        ),
      );
      const first = nodes[0],
        last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", fn);
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, []);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h2>{title}</h2>
          <button
            className="modal-close"
            aria-label="Close details"
            onClick={onClose}
          >
            <X />
          </button>
        </header>
        <div className="modal-body">{children}</div>
      </section>
    </div>
  );
}
function downloadReport(report: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "newhotmusic-email-health-report.json";
  a.click();
  URL.revokeObjectURL(url);
}
function SettingsPage({
  settings,
  busy,
  save,
  domainId,
}: {
  settings: Settings;
  busy: boolean;
  save: (fn: () => Promise<unknown>, msg: string) => void;
  domainId: number;
}) {
  const [monitoring, setMonitoring] = useState<Monitoring>(settings.monitoring);
  const [domainName, setDomainName] = useState(settings.domain.name);
  const [selectors, setSelectors] = useState(
    settings.domain.selectors.join(", "),
  );
  const [ips, setIps] = useState(settings.sending_ips.join(", "));
  const split = (value: string) =>
    value
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
  async function seed(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    save(
      () =>
        api(`/seeds/${domainId}`, {
          method: "POST",
          body: JSON.stringify(data),
        }),
      "Seed mailbox saved securely.",
    );
    form.reset();
  }
  return (
    <div className="settings-grid">
      <section className="panel settings-panel">
        <h3>Domain & sending infrastructure</h3>
        <p>Monitor the domain and IP addresses you control.</p>
        <label>
          Domain
          <input
            value={domainName}
            onChange={(e) => setDomainName(e.target.value)}
          />
        </label>
        <label>
          DKIM selectors
          <input
            value={selectors}
            onChange={(e) => setSelectors(e.target.value)}
            placeholder="default, selector1"
          />
          <small>Comma-separated selectors from your email provider.</small>
        </label>
        <label>
          Sending IPs
          <input
            value={ips}
            onChange={(e) => setIps(e.target.value)}
            placeholder="Public sending IPs, comma-separated"
          />
        </label>
        <button
          className="primary"
          disabled={busy}
          onClick={() =>
            save(
              () =>
                api(`/domains/${domainId}`, {
                  method: "PUT",
                  body: JSON.stringify({
                    name: domainName,
                    selectors: split(selectors),
                    sending_ips: split(ips),
                  }),
                }),
              "Domain settings saved.",
            )
          }
        >
          Save domain settings
        </button>
      </section>
      <section className="panel settings-panel">
        <h3>Connected integrations</h3>
        <p>Credential values stay on the backend.</p>
        {Object.entries(settings.integrations).map(([name, ready]) => (
          <div className="integration-row" key={name}>
            <span>{name}</span>
            <Badge state={ready ? "Configured" : "Not Configured"} />
          </div>
        ))}
        <p className="subtle">
          SMTP host, port, credentials, sender, alert recipients, AbuseIPDB key,
          licensed DNSBL sources, and webhook secret are configured through the
          server environment. See deployment documentation.
        </p>
      </section>
      <section className="panel settings-panel">
        <h3>Monitoring schedule & thresholds</h3>
        {Object.entries(monitoring.intervals).map(([group, seconds]) => (
          <label key={group}>
            {group} interval (minutes)
            <input
              type="number"
              min={5}
              value={seconds / 60}
              onChange={(e) =>
                setMonitoring({
                  ...monitoring,
                  intervals: {
                    ...monitoring.intervals,
                    [group]: Number(e.target.value) * 60,
                  },
                })
              }
            />
          </label>
        ))}
        {(
          [
            "bounce_threshold",
            "failure_threshold",
            "alert_cooldown",
            "health_healthy",
            "health_excellent",
          ] as const
        ).map((key) => (
          <label key={key}>
            {key.replaceAll("_", " ")}
            {key === "alert_cooldown" ? " (seconds)" : ""}
            <input
              type="number"
              value={monitoring[key]}
              onChange={(e) =>
                setMonitoring({ ...monitoring, [key]: Number(e.target.value) })
              }
            />
          </label>
        ))}
        <button
          className="primary"
          disabled={busy}
          onClick={() =>
            save(
              () =>
                api("/settings", {
                  method: "PUT",
                  body: JSON.stringify(monitoring),
                }),
              "Monitoring preferences saved.",
            )
          }
        >
          Save monitoring preferences
        </button>
      </section>
      <section className="panel settings-panel">
        <h3>Authorized seed mailboxes</h3>
        <p>Only add test mailboxes you own or have permission to access.</p>
        {settings.seeds
          .filter((s) => s.active)
          .map((s) => (
            <div className="integration-row" key={s.id}>
              <div>
                <strong>{s.provider}</strong>
                <small>{s.email}</small>
              </div>
              <button
                className="text-button"
                disabled={busy}
                onClick={() =>
                  save(
                    () => api(`/seeds/${s.id}`, { method: "DELETE" }),
                    "Mailbox disabled.",
                  )
                }
              >
                Disable
              </button>
            </div>
          ))}
        <form onSubmit={seed}>
          <label>
            Provider
            <select name="provider">
              <option>Gmail</option>
              <option>Outlook</option>
              <option>IMAP</option>
            </select>
          </label>
          <label>
            Test email address
            <input name="email" type="email" required />
          </label>
          <label>
            IMAP host
            <input name="imap_host" required placeholder="imap.gmail.com" />
          </label>
          <label>
            Inbox folder
            <input name="inbox_folder" defaultValue="INBOX" required />
          </label>
          <label>
            Spam folder
            <input
              name="spam_folder"
              required
              placeholder="[Gmail]/Spam or Junk"
            />
          </label>
          <label>
            App password
            <input
              name="password"
              type="password"
              autoComplete="new-password"
              required
            />
          </label>
          <p className="subtle">
            Encrypted at rest. Providers requiring OAuth need an OAuth adapter;
            ordinary passwords may not be accepted.
          </p>
          <button className="primary" disabled={busy}>
            Add authorized mailbox
          </button>
        </form>
      </section>
      <section className="panel settings-panel">
        <h3>Team access</h3>
        <p>Create separate accounts with administrator or read-only access.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            save(
              () =>
                api("/users", {
                  method: "POST",
                  body: JSON.stringify(Object.fromEntries(new FormData(form))),
                }),
              "Team account created.",
            );
            form.reset();
          }}
        >
          <label>
            Email
            <input type="email" name="email" required />
          </label>
          <label>
            Initial password
            <input
              type="password"
              name="password"
              minLength={12}
              required
              autoComplete="new-password"
            />
          </label>
          <label>
            Role
            <select name="role">
              <option value="viewer">Read-only viewer</option>
              <option value="admin">Administrator</option>
            </select>
          </label>
          <button className="primary" disabled={busy}>
            Create account
          </button>
        </form>
      </section>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
