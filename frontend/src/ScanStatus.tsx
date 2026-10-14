import { Scan, when } from "./api";
export default function ScanStatus({ scans }: { scans: Scan[] }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h3>Automated monitoring</h3>
        <span className="subtle">
          Public DNS & SMTP · every 5 minutes by default
        </span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>Status</th>
              <th>Last successful scan</th>
              <th>Next scheduled</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody>
            {scans.map((s) => (
              <tr key={s.group}>
                <td>
                  {s.group}
                  <br />
                  <small>
                    Every {Math.round(s.interval_seconds / 60)} minutes
                  </small>
                </td>
                <td>
                  {s.state}
                  {s.error && <small> · {s.error}</small>}
                </td>
                <td>
                  {s.last_success_at
                    ? when(s.last_success_at)
                    : "No successful scan yet"}
                </td>
                <td>
                  {s.next_due_at ? when(s.next_due_at) : "Awaiting scheduler"}
                </td>
                <td>
                  {s.duration_seconds == null
                    ? "Not measured"
                    : s.duration_seconds.toFixed(1) + "s"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
