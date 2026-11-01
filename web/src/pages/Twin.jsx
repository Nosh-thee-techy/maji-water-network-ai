import { useDesk } from "../desk.jsx";
import { Map, Strip } from "../widgets.jsx";

export default function Twin() {
  const { win, node, setNode, snap, setSnap, reconSnap } = useDesk();
  if (!win) return null;
  return (
    <div className="page">
      <Strip win={win} />
      <section className="pane tall">
        <h2>Pressure twin</h2>
        {win.recon?.available ? (
          <>
            <div className="kpis">
              <div className="kpi">
                <span>Field MAE</span>
                <b>{win.recon.mae_m.toFixed(2)} m</b>
              </div>
              <div className="kpi">
                <span>Leak TPR</span>
                <b>0.00</b>
              </div>
              <div className="kpi">
                <span>Used for dig?</span>
                <b>No</b>
              </div>
            </div>
            <div>
              {(win.recon.snapshots || []).map((s) => (
                <button key={s.window} className={`btn slim ghost ${snap === s.window ? "on" : ""}`} onClick={() => setSnap(s.window)}>
                  {s.window} · {s.mae_m.toFixed(2)} m
                </button>
              ))}
            </div>
            <Map map={win.map} selected={node} onPick={setNode} pressure={reconSnap?.p_hat_m} />
            <p className="inspect">
              {node && reconSnap?.p_hat_m[node] != null ? (
                <>
                  <em>{node}</em> reconstructed {reconSnap.p_hat_m[node].toFixed(1)} m · true {reconSnap.p_true_m[node]?.toFixed(1)} m
                </>
              ) : (
                win.recon.note
              )}
            </p>
          </>
        ) : (
          <p className="quiet">No checkpoint. Leftover does not wait on this net.</p>
        )}
      </section>
    </div>
  );
}
