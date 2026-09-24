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
import RequireSubscription from "./auth/RequireSubscription";
import AdminLayout from "./components/AdminLayout";
import AdminDashboard from "./pages/admin/AdminDashboard";
import AdminSubscriptions from "./pages/admin/AdminSubscriptions";
import AdminCampaigns from "./pages/admin/AdminCampaigns";
import AdminUsers from "./pages/admin/AdminUsers";
import AdminScannerCampaign from "./pages/admin/AdminScannerCampaign";
import AdminQuantileOrders from "./pages/admin/AdminQuantileOrders";
import Education from "./pages/Education";
import Pricing from "./pages/Pricing";
import Vision from "./pages/Vision";

export default function App() {
  return (
    <Routes>
      {/* Outside AppShell — Cognito's redirect lands here directly, no
          header/footer needed while the code exchange is in flight. */}
      <Route path="/auth/callback" element={<Callback />} />

      <Route element={<AppShell />}>
        <Route path="/" element={<Home />} />
        <Route path="/capabilities" element={<Capabilities />} />
        <Route
          path="/scanner"
          element={
            <RequireSubscription>
              <Scanner />
            </RequireSubscription>
          }
        />
        <Route
          path="/markets/chart"
          element={
            <RequireSubscription>
              <Chart />
            </RequireSubscription>
          }
        />
        <Route path="/news" element={<News />} />
        <Route
          path="/markets/ipo-hub"
          element={
            <RequireSubscription>
              <IpoHub />
            </RequireSubscription>
          }
        />
        <Route
          path="/markets/research"
          element={
            <RequireSubscription>
              <Research />
            </RequireSubscription>
          }
        />
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
        <Route
          path="/markets/chart-wall"
          element={
            <RequireSubscription>
              <ChartWall />
            </RequireSubscription>
          }
        />

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
          <Route path="scanner-campaign" element={<AdminScannerCampaign />} />
          <Route path="quantile-orders" element={<AdminQuantileOrders />} />
        </Route>

        <Route path="/education" element={<Education />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/vision" element={<Vision />} />
      </Route>
    </Routes>
  );
}
