export async function api(path, opts) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export function shortCase(s) {
  const id = s.scenario_id || "";
  if (id.includes("clean")) return { title: "Clean", detail: "Tanks fill. No leftover.", tone: "" };
  if (id.includes("longfill")) return { title: "Long fill", detail: "120 min tanks. Same leak.", tone: "hot" };
  if (id.includes("valve")) return { title: "Valve", detail: "Scheduled. No fill surge.", tone: "fault" };
  if (id.includes("leak")) return { title: "Leak · J07", detail: "1.5 L/s leftover after t_sat.", tone: "hot" };
  return { title: s.label || id, detail: id, tone: "" };
}

export function Hydrograph({ data, cursor, onPick }) {
  if (!data?.t_h?.length) return null;
  const t = data.t_h;
  const q = data.q_clean_lps.map((v) => (v == null ? 0 : v));
  const up = (data.q_uplink_lps || q).map((v) => (v == null ? 0 : v));
  const w = 720;
  const h = 320;
  const pad = { l: 48, r: 16, t: 26, b: 34 };
  const t0 = Math.min(...t);
  const t1 = Math.max(...t);
  const q1 = Math.max(1, ...q, ...up) * 1.12;
  const X = (v) => pad.l + ((v - t0) / (t1 - t0 || 1)) * (w - pad.l - pad.r);
  const Y = (v) => pad.t + (1 - v / q1) * (h - pad.t - pad.b);
  const line = t.map((ti, i) => `${i ? "L" : "M"}${X(ti)},${Y(q[i])}`).join(" ");
  const uplink = t.map((ti, i) => `${i ? "L" : "M"}${X(ti)},${Y(up[i])}`).join(" ");
  const area = `${line} L${X(t[t.length - 1])},${Y(0)} L${X(t[0])},${Y(0)} Z`;
  const sat = (data.t_sat_h || []).filter((x) => x >= t0 && x <= t1);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * q1);
  const pick = (evt) => {
    const box = evt.currentTarget.getBoundingClientRect();
    const x = ((evt.clientX - box.left) / box.width) * w;
    const frac = Math.min(1, Math.max(0, (x - pad.l) / (w - pad.l - pad.r)));
    const hour = t0 + frac * (t1 - t0);
    let best = 0;
    let dist = 1e9;
    t.forEach((ti, i) => {
      const d0 = Math.abs(ti - hour);
      if (d0 < dist) {
        dist = d0;
        best = i;
      }
    });
    onPick({ hour: t[best], q: q[best] });
  };
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} onClick={pick}>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={w - pad.r} y1={Y(v)} y2={Y(v)} stroke="#1c3034" />
          <text x={8} y={Y(v) + 4} fontSize="10" fill="#7f9692" fontFamily="IBM Plex Mono, monospace">
            {v.toFixed(1)}
          </text>
        </g>
      ))}
      <path d={area} fill="rgba(58, 212, 199, 0.16)" />
      <path d={uplink} fill="none" stroke="#6d8681" strokeWidth="1.4" />
      <path d={line} fill="none" stroke="#3ad4c7" strokeWidth="2.6" strokeLinejoin="round" />
      {sat.map((s) => (
        <g key={s}>
          <line x1={X(s)} x2={X(s)} y1={pad.t} y2={h - pad.b} stroke="#e67a2e" strokeDasharray="5 4" />
          <text x={X(s) + 6} y={pad.t + 12} fontSize="11" fill="#e67a2e">
            tanks full
          </text>
        </g>
      ))}
      {cursor && (
        <g>
          <line x1={X(cursor.hour)} x2={X(cursor.hour)} y1={pad.t} y2={h - pad.b} stroke="#e7f1ee" />
          <circle cx={X(cursor.hour)} cy={Y(cursor.q)} r="4.5" fill="#e67a2e" />
          <text x={X(cursor.hour) + 6} y={Y(cursor.q) - 8} fontSize="11" fill="#e7f1ee" fontFamily="IBM Plex Mono, monospace">
            {cursor.q.toFixed(2)} L/s
          </text>
        </g>
      )}
      <text x={pad.l} y={h - 8} fontSize="11" fill="#7f9692" fontFamily="IBM Plex Mono, monospace">
        {t0.toFixed(0)} h
      </text>
      <text x={w - 48} y={h - 8} fontSize="11" fill="#7f9692" fontFamily="IBM Plex Mono, monospace">
        {t1.toFixed(0)} h
      </text>
    </svg>
  );
}

function heat(t) {
  const a = [46, 200, 188];
  const b = [230, 122, 46];
  const c = a.map((u, i) => Math.round(u + (b[i] - u) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export function Map({ map, selected, onPick, pressure }) {
  if (!map?.nodes?.length) return null;
  const xs = map.nodes.map((n) => n.x);
  const ys = map.nodes.map((n) => n.y);
  const minX = Math.min(...xs) - 36;
  const maxX = Math.max(...xs) + 36;
  const minY = Math.min(...ys) - 36;
  const maxY = Math.max(...ys) + 44;
  const byId = Object.fromEntries(map.nodes.map((n) => [n.id, n]));
  const pred = new Set(map.predicted || []);
  const sensors = new Set(map.sensors || []);
  const vals = pressure ? Object.values(pressure) : [];
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 1;
  return (
    <svg className="map" viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`}>
      {map.pipes.map((p) => {
        const a = byId[p.a];
        const b = byId[p.b];
        if (!a || !b) return null;
        return <line key={p.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#3d5a60" strokeWidth="4" />;
      })}
      {map.nodes.map((n) => {
        let fill = pred.has(n.id) ? "#e67a2e" : sensors.has(n.id) ? "#2ec8bc" : n.id === "R1" ? "#e7f1ee" : "#1a2c2f";
        if (pressure && pressure[n.id] != null && n.id !== "R1") {
          fill = heat((pressure[n.id] - lo) / (hi - lo || 1));
        }
        const hit = selected === n.id;
        return (
          <g key={n.id} onClick={() => onPick(n.id)} style={{ cursor: "pointer" }}>
            {pred.has(n.id) && !pressure && (
              <circle cx={n.x} cy={n.y} r="16" fill="none" stroke="#f08a3a" strokeOpacity="0.55" />
            )}
            <circle cx={n.x} cy={n.y} r={hit ? 11 : pred.has(n.id) ? 9 : 7.5} fill={fill} stroke="#f3f8f6" strokeWidth={hit ? 2 : 1} />
            <text x={n.x + 10} y={n.y - 9} fontSize="11" fill="#e7f1ee">
              {n.id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

const STEPS = ["open", "assigned", "repaired", "verified"];

export function CrewSteps({ state }) {
  const i = Math.max(0, STEPS.indexOf(state));
  return (
    <div className="steps">
      {STEPS.map((s, n) => (
        <i key={s} className={n < i ? "done" : n === i ? "on" : ""}>
          {s}
        </i>
      ))}
    </div>
  );
}

export function Strip({ win }) {
  if (!win) return null;
  return (
    <div className="strip">
      <div className="readouts">
        <div className="readout">
          <span>Leftover</span>
          <b>{win.leftover_lps.toFixed(2)} L/s</b>
        </div>
        <div className="readout">
          <span>PBC</span>
          <b>{win.leftover_m3_per_day.toFixed(1)} m³/d</b>
        </div>
        <div className="readout">
          <span>Supplied</span>
          <b>{win.balance.supplied_m3.toFixed(1)} m³</b>
        </div>
      </div>
      <div className={`pill ${win.event}`}>{win.event.replaceAll("_", " ")}</div>
    </div>
  );
}

export function Call({ win, canOpen, busy, onOpen }) {
  return (
    <section className="verdict">
      <h2>Call</h2>
      <h1>{win.story.headline}</h1>
      <ol className="beats">
        {win.story.beats.map((b) => (
          <li key={b.title}>
            <strong>{b.title}</strong>
            {b.body}
          </li>
        ))}
      </ol>
      <div className="action">{win.story.action}</div>
      {canOpen ? (
        <button className="btn" disabled={busy} onClick={onOpen}>
          Open a job from this leftover
        </button>
      ) : (
        <p className="quiet">No dig. Leftover is below the 0.35 L/s floor — or this is a valve/sensor fault.</p>
      )}
      {win.banner?.is_actionable_fault && (
        <button className="btn ghost" disabled={busy} onClick={onOpen} style={{ marginTop: 8 }}>
          Open a fault job
        </button>
      )}
    </section>
  );
}
