import { useDesk } from "../desk.jsx";
import { Map, Strip } from "../widgets.jsx";

export default function Network() {
  const { win, node, setNode } = useDesk();
  if (!win) return null;
  return (
    <div className="page">
      <Strip win={win} />
      <div className="split">
        <section className="pane tall">
          <h2>DMA · click a junction</h2>
          <Map map={win.map} selected={node} onPick={setNode} />
          <p className="inspect">
            {node ? (
              <>
                <em>{node}</em>
                {win.map.predicted.includes(node)
                  ? " is on the dig list."
                  : win.map.sensors.includes(node)
                    ? " is a pressure sensor."
                    : node === "R1"
                      ? " is the reservoir."
                      : " is a junction."}
              </>
            ) : (
              "Cyan = sensor. Orange = suggested dig."
            )}
          </p>
        </section>
        <section className="crew">
          <h2>Dig list</h2>
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
                    <td>±{r.uncertainty_radius_hops} hops</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="quiet">No dig list on this window. Leftover never rose, or the valve never opened.</p>
          )}
        </section>
      </div>
    </div>
  );
}
