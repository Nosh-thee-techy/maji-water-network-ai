import { useDesk } from "../desk.jsx";
import { api, Call, Hydrograph, Strip } from "../widgets.jsx";

export default function Inlet() {
  const { win, sid, cursor, setCursor, setAt, at, canOpen, busy, openJob } = useDesk();
  if (!win) return null;
  return (
    <div className="page">
      <Strip win={win} />
      <div className="split">
        <section className="hero">
          <div className="hero-head">
            <h2>Inlet hydrograph</h2>
            <span className="hint">Teal = inlet. Grey = uplink. Click a time — the brief is not a leak call.</span>
          </div>
          <Hydrograph
            data={win.hydrograph}
            cursor={cursor}
            onPick={(c) => {
              setCursor(c);
              api(`/api/windows/${sid}/at?hour=${c.hour}&q=${c.q}`).then(setAt).catch(() => setAt(null));
            }}
          />
          <div className={`brief ${at?.phase || ""}`}>
            {at ? (
              <>
                <strong>{at.title}.</strong> {at.body}
              </>
            ) : (
              "The knee on this plot is t_sat. After that, leftover litres per second is the leak test."
            )}
          </div>
        </section>
        <Call win={win} canOpen={canOpen} busy={busy} onOpen={openJob} />
      </div>
    </div>
  );
}
