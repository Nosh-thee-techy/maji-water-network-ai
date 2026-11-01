import { Link } from "react-router-dom";
import { useDesk } from "../desk.jsx";
import { Call, CrewSteps, Strip } from "../widgets.jsx";

export default function Crew() {
  const { win, sid, mine, crew, setCrew, busy, step, canOpen, openJob, node, setNode } = useDesk();
  if (!win) return null;
  return (
    <div className="page">
      <Strip win={win} />
      <div className="split">
        <section className="crew">
          <h2>Crew desk</h2>
          {win.dig.length ? (
            <table className="dig">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Node</th>
                  <th>L/s</th>
                  <th>Radius</th>
                </tr>
              </thead>
              <tbody>
                {win.dig.map((r) => (
                  <tr key={r.node} className={node === r.node ? "on" : ""} onClick={() => setNode(r.node)}>
                    <td>{r.rank}</td>
                    <td>{r.node}</td>
                    <td>{r.q_lps.toFixed(2)}</td>
                    <td>±{r.uncertainty_radius_hops}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="quiet">No dig list on this window.</p>
          )}
          <div className="field">
            <input value={crew} onChange={(e) => setCrew(e.target.value)} placeholder="Crew name" />
          </div>
          {mine.length === 0 && (
            <p className="quiet" style={{ marginTop: 12 }}>
              No open job yet. Open one from the call, then assign → repair → verify leftover fell.
            </p>
          )}
          {mine.map((ev) => (
            <div className="job" key={ev.event_id}>
              <strong>{ev.event_id}</strong>
              <small>
                {ev.kind} · leftover {ev.leftover_open_lps.toFixed(2)} L/s · {ev.nodes.join(", ") || "—"}
              </small>
              <CrewSteps state={ev.state} />
              {["open", "assigned"].includes(ev.state) && (
                <button className="btn" disabled={busy || !crew.trim()} onClick={() => step(ev.event_id, "assign", { name: crew })}>
                  Assign {crew}
                </button>
              )}
              {["assigned", "failed_verify"].includes(ev.state) && (
                <button className="btn warn" disabled={busy} onClick={() => step(ev.event_id, "repair", { simulated: true })}>
                  Mark repaired (simulated)
                </button>
              )}
              {ev.state === "repaired" && (
                <button className="btn" disabled={busy} onClick={() => step(ev.event_id, "verify", { leftover_now_lps: 0 })}>
                  Verify leftover fell
                </button>
              )}
              {ev.state === "verified" && <p className="quiet">Closed. Leftover after verify: {ev.leftover_verify_lps} L/s.</p>}
            </div>
          ))}
          <p className="inspect">
            <Link to={{ pathname: "/", search: `?w=${sid}` }}>Back to the inlet</Link>
          </p>
        </section>
        <Call win={win} canOpen={canOpen} busy={busy} onOpen={openJob} />
      </div>
    </div>
  );
}
