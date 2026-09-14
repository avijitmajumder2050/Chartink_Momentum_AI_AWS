import { Routes, Route } from "react-router-dom";
import AppShell from "./components/AppShell";
import Home from "./pages/Home";
import Capabilities from "./pages/Capabilities";
import Scanner from "./pages/Scanner";
import Chart from "./pages/Chart";
import News from "./pages/News";
import IpoHub from "./pages/IpoHub";
import Research from "./pages/Research";
import Subscription from "./pages/Subscription";
import Callback from "./auth/Callback";
import RequireAuth from "./auth/RequireAuth";

export default function App() {
  return (
    <Routes>
      {/* Outside AppShell — Cognito's redirect lands here directly, no
          header/footer needed while the code exchange is in flight. */}
      <Route path="/auth/callback" element={<Callback />} />

      <Route element={<AppShell />}>
        <Route path="/" element={<Home />} />
        <Route path="/capabilities" element={<Capabilities />} />
        <Route path="/scanner" element={<Scanner />} />
        <Route path="/markets/chart" element={<Chart />} />
        <Route path="/news" element={<News />} />
        <Route path="/markets/ipo-hub" element={<IpoHub />} />
        <Route path="/markets/research" element={<Research />} />
        <Route
          path="/subscription"
          element={
            <RequireAuth>
              <Subscription />
            </RequireAuth>
          }
        />
        {/* Every other route from the original app (News, Markets/*,
            Education, Pricing, Dashboard, Admin/*, ...) gets added here
            page-by-page in later phases of the rewrite plan. */}
      </Route>
    </Routes>
  );
}
