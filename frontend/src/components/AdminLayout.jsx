import { Outlet } from "react-router-dom";
import AdminSidebar from "./AdminSidebar";

// Every admin page's `<div style="display:flex">{sidebar}{content}</div>`
// wrapper, factored out once instead of repeated per page.
export default function AdminLayout() {
  return (
    <div style={{ width: "100%", display: "flex" }}>
      <AdminSidebar />
      <div style={{ flex: 1 }}>
        <Outlet />
      </div>
    </div>
  );
}
