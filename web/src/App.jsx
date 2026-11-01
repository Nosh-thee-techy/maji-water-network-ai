import { NavLink, Outlet, Route, Routes } from "react-router-dom";
import { DeskProvider, useDesk } from "./desk.jsx";
import { shortCase } from "./widgets.jsx";
import Inlet from "./pages/Inlet.jsx";
import Network from "./pages/Network.jsx";
import Twin from "./pages/Twin.jsx";
import Crew from "./pages/Crew.jsx";

const PAGES = [
  { to: "/", label: "Inlet", end: true },
  { to: "/network", label: "Network" },
  { to: "/twin", label: "Twin" },
  { to: "/crew", label: "Crew" },
];

function Layout() {
  const { list, sid, setSid, err, win } = useDesk();
  const q = sid ? `?w=${sid}` : "";
  return (
    <div className="app">
      <aside className="rail">
        <div className="mark">
          <strong>MAJI</strong>
          <span>IWS leftover</span>
        </div>
        <p className="place">Al-Washali DMA · four simulated windows</p>
        <nav className="pages">
          {PAGES.map((p) => (
            <NavLink key={p.to} to={`${p.to}${q}`} end={p.end} className={({ isActive }) => (isActive ? "on" : "")}>
              {p.label}
            </NavLink>
          ))}
        </nav>
        <div className="cases">
          {list.map((s) => {
            const c = shortCase(s);
            return (
              <button
                key={s.scenario_id}
                data-id={s.scenario_id}
                className={`case ${c.tone} ${sid === s.scenario_id ? "on" : ""}`}
                onClick={() => setSid(s.scenario_id)}
              >
                <b>{c.title}</b>
                <small>{c.detail}</small>
              </button>
            );
          })}
        </div>
      </aside>
      <main className="stage">
        {err && <p className="err">{err}</p>}
        {!win && !err && <p className="loading">Reading the inlet…</p>}
        {win && <Outlet />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <DeskProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Inlet />} />
          <Route path="/network" element={<Network />} />
          <Route path="/twin" element={<Twin />} />
          <Route path="/crew" element={<Crew />} />
        </Route>
      </Routes>
    </DeskProvider>
  );
}
