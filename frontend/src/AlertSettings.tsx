import { useEffect, useState } from "react";
import { api, when, AlertPolicy, AlertStatus } from "./api";
export default function AlertSettings({
  domainId,
  busy,
  save,
}: {
  domainId: number;
  busy: boolean;
  save: (fn: () => Promise<unknown>, msg: string) => void;
}) {
  const [status, setStatus] = useState<AlertStatus | null>(null);
  const [policy, setPolicy] = useState<AlertPolicy | null>(null);
  const [error, setError] = useState("");
  const [recipientText, setRecipientText] = useState<string | null>(null);
  async function refresh() {
    try {
      const data = await api<AlertStatus>(`/alerts/${domainId}`);
      setStatus(data);
      setPolicy((p) => p || data.settings || null);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [domainId]);
  const submit = (next: AlertPolicy) =>
    save(async () => {
      const data = await api<AlertPolicy>(`/alerts/${domainId}/settings`, {
        method: "PUT",
        body: JSON.stringify({
          ...next,
          recipients: (recipientText ?? next.recipients.join(","))
            .split(",")
            .map((v) => v.trim())
            .filter(Boolean),
        }),
      });
      setPolicy(data);
      await refresh();
    }, "Alert preferences saved. Monitoring continues independently.");
  return (
    <section className="panel settings-panel">
      <h3>Email alert settings</h3>
      <p>
        One diagnostic digest per domain, with evidence and practical
        verification steps. Only observed recovery stops a problem notification.
      </p>
      {error && <p role="alert">{error}</p>}
      {policy && (
        <>
          <div className="alert-controls">
            <button
              className={policy.enabled ? "primary" : "secondary"}
              disabled={busy}
              onClick={() => submit({ ...policy, enabled: !policy.enabled })}
            >
              {policy.enabled ? "Disable email alerts" : "Enable email alerts"}
            </button>
            <button
              className="secondary"
              disabled={busy || !policy.enabled}
              onClick={() => submit({ ...policy, paused: !policy.paused })}
            >
              {policy.paused ? "Resume alerts" : "Pause alerts"}
            </button>
          </div>
          <label>
            Alert recipients
            <input
              value={recipientText ?? policy.recipients.join(", ")}
              onChange={(e) => setRecipientText(e.target.value)}
              placeholder="team@your-domain.com"
            />
          </label>
          <label>
            Reminder interval (minutes)
            <input
              type="number"
              min={5}
              max={1440}
              value={policy.reminder_seconds / 60}
              onChange={(e) =>
                setPolicy({
                  ...policy,
                  reminder_seconds: Number(e.target.value) * 60,
                })
              }
            />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={policy.critical_only}
              onChange={(e) =>
                setPolicy({ ...policy, critical_only: e.target.checked })
              }
            />
            Critical-only alerts
          </label>
          <div className="alert-controls">
            <button
              className="primary"
              disabled={busy}
              onClick={() => submit(policy)}
            >
              Save alert settings
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                save(
                  () => api(`/alerts/${domainId}/test`, { method: "POST" }),
                  "Test email queued; check its actual delivery status below.",
                )
              }
            >
              Send test email
            </button>
          </div>
        </>
      )}
      {status && (
        <>
          <p>
            Last alert sent: {when(status.last_sent)}
            <br />
            Last delivery status: <strong>{status.last_delivery_status}</strong>
          </p>
          <details>
            <summary>Alert history ({status.history.length})</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Type / time</th>
                    <th>Status</th>
                    <th>Attempts / detail</th>
                  </tr>
                </thead>
                <tbody>
                  {status.history.map((a) => (
                    <tr key={a.id}>
                      <td>
                        {a.kind}
                        <br />
                        {when(a.created_at)}
                      </td>
                      <td>{a.state}</td>
                      <td>
                        {a.attempts} · {a.suppression_reason || a.error || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
