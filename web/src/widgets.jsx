import { useState } from "react";

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

function nearestSample(t, hour) {
  let best = 0;
  let dist = 1e9;
  t.forEach((ti, i) => {
    const d0 = Math.abs(ti - hour);
    if (d0 < dist) {
      dist = d0;
      best = i;
    }
  });
  return best;
}

function openBands(t0, t1) {
  const out = [];
  const startDay = Math.floor(t0 / 24);
  const endDay = Math.floor(t1 / 24);
  for (let d = startDay; d <= endDay; d++) {
    for (const [a, b] of [
      [5, 9],
      [17, 21],
    ]) {
      const lo = Math.max(t0, d * 24 + a);
      const hi = Math.min(t1, d * 24 + b);
      if (hi > lo) out.push([lo, hi]);
    }
  }
  return out;
}

export function Hydrograph({ data, cursor, onPick }) {
  const [hover, setHover] = useState(null);
  if (!data?.t_h?.length) return null;
  const t = data.t_h;
  const q = data.q_clean_lps.map((v) => (v == null ? 0 : v));
  const up = (data.q_uplink_lps || q).map((v) => (v == null ? 0 : v));
  const w = 720;
  const h = 340;
  const pad = { l: 52, r: 18, t: 28, b: 36 };
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
  const atEvent = (evt) => {
    const box = evt.currentTarget.getBoundingClientRect();
    const x = ((evt.clientX - box.left) / box.width) * w;
    const frac = Math.min(1, Math.max(0, (x - pad.l) / (w - pad.l - pad.r)));
    const hour = t0 + frac * (t1 - t0);
    const i = nearestSample(t, hour);
    return { hour: t[i], q: q[i], up: up[i] };
  };
  const mark = hover || cursor;
  return (
    <div className="graph-frame chart-frame">
      <svg
        className="chart"
        viewBox={`0 0 ${w} ${h}`}
        onPointerMove={(e) => setHover(atEvent(e))}
        onPointerLeave={() => setHover(null)}
        onPointerDown={(e) => {
          e.preventDefault();
          const c = atEvent(e);
          setHover(c);
          onPick(c);
        }}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={w - pad.r} y1={Y(v)} y2={Y(v)} stroke="#24383c" />
            <text x={8} y={Y(v) + 4} fontSize="11" fill="#a6bbb6" fontFamily="IBM Plex Mono, monospace">
              {v.toFixed(1)}
            </text>
          </g>
        ))}
        {openBands(t0, t1).map(([a, b]) => (
          <rect key={`${a}-${b}`} x={X(a)} y={pad.t} width={X(b) - X(a)} height={h - pad.t - pad.b} fill="rgba(58, 212, 199, 0.07)" />
        ))}
        {sat.map((s) => (
          <rect key={`leftover-${s}`} x={X(s)} y={pad.t} width={Math.max(0, X(Math.min(t1, Math.floor(s / 24) * 24 + (s % 24 < 12 ? 9 : 21))) - X(s))} height={h - pad.t - pad.b} fill="rgba(240, 138, 58, 0.1)" />
        ))}
        <path d={area} fill="rgba(58, 212, 199, 0.18)" />
        <path d={uplink} fill="none" stroke="#8aa19c" strokeWidth="1.6" />
        <path d={line} fill="none" stroke="#3ad4c7" strokeWidth="3" strokeLinejoin="round" />
        {sat.map((s) => (
          <g key={s}>
            <line x1={X(s)} x2={X(s)} y1={pad.t} y2={h - pad.b} stroke="#f08a3a" strokeDasharray="5 4" strokeWidth="1.6" />
            <text x={X(s) + 6} y={pad.t + 14} fontSize="12" fill="#f08a3a">
              tanks full
            </text>
          </g>
        ))}
        {mark && (
          <g>
            <line x1={X(mark.hour)} x2={X(mark.hour)} y1={pad.t} y2={h - pad.b} stroke={hover && !cursor ? "#a6bbb6" : "#f3f8f6"} strokeWidth="1.4" />
            <circle cx={X(mark.hour)} cy={Y(mark.q)} r="6" fill="#f08a3a" stroke="#f3f8f6" strokeWidth="1.4" />
          </g>
        )}
        <text x={8} y={14} fontSize="11" fill="#a6bbb6">
          L/s
        </text>
        <text x={pad.l} y={h - 8} fontSize="11" fill="#a6bbb6" fontFamily="IBM Plex Mono, monospace">
          {t0.toFixed(0)} h
        </text>
        <text x={w - 52} y={h - 8} fontSize="11" fill="#a6bbb6" fontFamily="IBM Plex Mono, monospace">
          {t1.toFixed(0)} h
        </text>
      </svg>
      {mark && (
        <div className="graph-card">
          <b>
            {mark.hour.toFixed(2)} h · {mark.q.toFixed(2)} L/s
          </b>
          <span>{hover ? "Press to lock this hour. The brief is not a leak call." : "Hour locked. The brief below is fill vs leftover vs closed."}</span>
        </div>
      )}
    </div>
  );
}

function heat(t) {
  const stops = [
    [26, 107, 114],
    [212, 195, 90],
    [230, 122, 46],
  ];
  const x = Math.min(1, Math.max(0, t)) * 2;
  const i = x < 1 ? 0 : 1;
  const f = x < 1 ? x : x - 1;
  const c = stops[i].map((u, k) => Math.round(u + (stops[i + 1][k] - u) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function nodeRole(id, pred, sensors) {
  if (id === "R1") return "Reservoir";
  if (pred.has(id)) return "On the dig list";
  if (sensors.has(id)) return "Pressure sensor";
  return "Junction";
}

export function Map({ map, selected, onPick, pressure, truth }) {
  const [hover, setHover] = useState(null);
  if (!map?.nodes?.length) return null;
  const xs = map.nodes.map((n) => n.x);
  const ys = map.nodes.map((n) => n.y);
  const minX = Math.min(...xs) - 28;
  const maxX = Math.max(...xs) + 56;
  const minY = Math.min(...ys) - 32;
  const maxY = Math.max(...ys) + 36;
  const byId = Object.fromEntries(map.nodes.map((n) => [n.id, n]));
  const pred = new Set(map.predicted || []);
  const sensors = new Set(map.sensors || []);
  const vals = pressure ? Object.values(pressure) : [];
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 1;
  const focus = hover || selected;
  const nbrs = new Set();
  if (focus) {
    map.pipes.forEach((p) => {
      if (p.a === focus) nbrs.add(p.b);
      if (p.b === focus) nbrs.add(p.a);
    });
  }
  const hat = focus && pressure ? pressure[focus] : null;
  const tru = focus && truth ? truth[focus] : null;
  return (
    <div className="graph-frame">
      <svg className="map" viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`} onPointerLeave={() => setHover(null)}>
        {map.pipes.map((p) => {
          const a = byId[p.a];
          const b = byId[p.b];
          if (!a || !b) return null;
          const lit = focus && (p.a === focus || p.b === focus);
          return (
            <line
              key={p.id}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={lit ? "#3ad4c7" : "#3d5a60"}
              strokeWidth={lit ? 7 : 5}
              opacity={focus && !lit ? 0.35 : 1}
            />
          );
        })}
        {map.nodes.map((n) => {
          let fill = pred.has(n.id) ? "#f08a3a" : sensors.has(n.id) ? "#3ad4c7" : n.id === "R1" ? "#f3f8f6" : "#24383c";
          if (pressure && pressure[n.id] != null && n.id !== "R1") {
            fill = heat((pressure[n.id] - lo) / (hi - lo || 1));
          }
          const on = selected === n.id;
          const over = hover === n.id;
          const dim = focus && n.id !== focus && !nbrs.has(n.id);
          const r = on || over ? 13 : pred.has(n.id) ? 11 : 10;
          const label = n.id;
          const chipW = label.length * 7.2 + 10;
          return (
            <g
              key={n.id}
              onPointerEnter={() => setHover(n.id)}
              onPointerDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onPick(n.id);
              }}
              style={{ cursor: "pointer" }}
              opacity={dim ? 0.4 : 1}
            >
              <circle cx={n.x} cy={n.y} r="22" fill="transparent" />
              {on && <circle cx={n.x} cy={n.y} r="18" fill="none" stroke="#f3f8f6" strokeWidth="1.6" />}
              {pred.has(n.id) && !pressure && <circle cx={n.x} cy={n.y} r="16" fill="none" stroke="#f08a3a" strokeOpacity="0.7" />}
              <circle cx={n.x} cy={n.y} r={r} fill={fill} stroke="#f3f8f6" strokeWidth={on || over ? 2.2 : 1.2} />
              <rect x={n.x + 12} y={n.y - 20} width={chipW} height={16} rx="3" fill="#10191c" stroke="#2a4146" />
              <text x={n.x + 16} y={n.y - 8} fontSize="12" fill="#f3f8f6">
                {label}
              </text>
              {pressure && pressure[n.id] != null && (on || over) && (
                <text x={n.x + 16} y={n.y + 22} fontSize="11" fill="#a6bbb6" fontFamily="IBM Plex Mono, monospace">
                  {pressure[n.id].toFixed(1)} m
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="graph-legend">
        {pressure ? (
          <>
            <i className="scale" />
            <span>
              {lo.toFixed(1)} m → {hi.toFixed(1)} m
            </span>
          </>
        ) : (
          <>
            <i className="dot water" />
            <span>Sensor</span>
            <i className="dot alert" />
            <span>Dig</span>
            <i className="dot paper" />
            <span>Reservoir</span>
          </>
        )}
      </div>
      {focus && (
        <div className="graph-card">
          <b>{focus}</b>
          <span>{nodeRole(focus, pred, sensors)}</span>
          {hat != null && (
            <span>
              Reconstructed {hat.toFixed(1)} m
              {tru != null ? ` · true ${tru.toFixed(1)} m · err ${Math.abs(hat - tru).toFixed(1)} m` : ""}
            </span>
          )}
          {nbrs.size > 0 && <span>Pipes to {[...nbrs].join(", ")}</span>}
          <span>{hover && hover !== selected ? "Press to pin this junction." : "Pinned. Press another node to move."}</span>
        </div>
      )}
    </div>
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
