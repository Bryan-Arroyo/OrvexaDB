"use client";

import { useEffect, useState } from "react";
import { invalidatePreviousSession } from "../lib/api";
import { Login, VISIT_KEY } from "./App";

export default function Home() {
  const [ready, setReady] = useState(false);
  useEffect(() => { window.sessionStorage.removeItem(VISIT_KEY); void invalidatePreviousSession().finally(() => setReady(true)); }, []);
  return <Login ready={ready} onLogin={() => window.location.assign("/dashboard")} />;
}
