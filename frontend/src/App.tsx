import { Navigate, Route, Routes } from "react-router-dom";
import { useAuthStore } from "./store/auth";
import LoginView from "./views/LoginView";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppShell() {
  return (
    <div id="app-shell">
      {/* Views will be added in Task 7 */}
      <p>Loading workspace…</p>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="/login" element={<LoginView />} />
      <Route
        path="/app/*"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
