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
import Dashboard from "./pages/Dashboard";
import ChartWall from "./pages/ChartWall";
import Callback from "./auth/Callback";
import RequireAuth from "./auth/RequireAuth";
import RequireAdmin from "./auth/RequireAdmin";
import AdminLayout from "./components/AdminLayout";
import AdminDashboard from "./pages/admin/AdminDashboard";
import AdminSubscriptions from "./pages/admin/AdminSubscriptions";
import AdminCampaigns from "./pages/admin/AdminCampaigns";
import AdminUsers from "./pages/admin/AdminUsers";

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
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <Dashboard />
            </RequireAuth>
          }
        />
        <Route path="/markets/chart-wall" element={<ChartWall />} />

        <Route
          path="/admin"
          element={
            <RequireAdmin>
              <AdminLayout />
            </RequireAdmin>
          }
        >
          <Route index element={<AdminDashboard />} />
          <Route path="users" element={<AdminUsers />} />
          <Route path="subscriptions" element={<AdminSubscriptions />} />
          <Route path="campaigns" element={<AdminCampaigns />} />
          {/* /admin/scanner-campaign added here once ported. */}
        </Route>

        {/* Remaining marketing/static pages (Education, Pricing, Vision)
            get added here in Phase 4 of the rewrite plan. */}
      </Route>
    </Routes>
  );
}
