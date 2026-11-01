import { createContext, useContext, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "./widgets.jsx";

const Desk = createContext(null);

export function useDesk() {
  return useContext(Desk);
}

export function DeskProvider({ children }) {
  const [params, setParams] = useSearchParams();
  const [list, setList] = useState([]);
  const [sid, setSidState] = useState(params.get("w"));
  const [win, setWin] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [crew, setCrew] = useState("DMA crew 2");
  const [cursor, setCursor] = useState(null);
  const [at, setAt] = useState(null);
  const [snap, setSnap] = useState("after");
  const [node, setNode] = useState(null);

  const setSid = (id) => {
    setSidState(id);
    const next = new URLSearchParams(params);
    if (id) next.set("w", id);
    else next.delete("w");
    setParams(next, { replace: true });
  };

  const loadJobs = () => api("/api/events").then(setJobs).catch(() => setJobs([]));

  useEffect(() => {
    api("/api/scenarios")
      .then((j) => {
        const rows = j.scenarios || [];
        setList(rows);
        const want = params.get("w");
        const ok = rows.some((r) => r.scenario_id === want);
        setSid(ok ? want : rows[0]?.scenario_id);
      })
      .catch((e) => setErr(String(e)));
    loadJobs();
  }, []);

  useEffect(() => {
    if (!sid) return;
    setWin(null);
    setCursor(null);
    setAt(null);
    setNode(null);
    api(`/api/windows/${sid}`)
      .then(setWin)
      .catch((e) => setErr(String(e)));
  }, [sid]);

  const act = async (fn) => {
    setBusy(true);
    setErr("");
    try {
      await fn();
      await loadJobs();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const openJob = () =>
    act(() =>
      api("/api/events", {
        method: "POST",
        body: JSON.stringify({
          scenario_id: win.id,
          kind: win.event,
          leftover_lps: win.leftover_lps,
          leftover_m3_day: win.leftover_m3_per_day,
          nodes: win.map.predicted,
          t_sat_s: win.t_sat_s || [],
        }),
      })
    );

  const step = (eid, action, body) =>
    act(() => api(`/api/events/${eid}/${action}`, { method: "POST", body: JSON.stringify(body || {}) }));

  const mine = jobs.filter((j) => j.scenario_id === sid);
  const canOpen = win && (win.banner?.is_leak || win.banner?.is_actionable_fault);
  const reconSnap = win?.recon?.snapshots?.find((s) => s.window === snap) || win?.recon?.snapshots?.[0];

  return (
    <Desk.Provider
      value={{
        list,
        sid,
        setSid,
        win,
        jobs,
        err,
        busy,
        crew,
        setCrew,
        cursor,
        setCursor,
        at,
        setAt,
        snap,
        setSnap,
        node,
        setNode,
        openJob,
        step,
        mine,
        canOpen,
        reconSnap,
      }}
    >
      {children}
    </Desk.Provider>
  );
}
