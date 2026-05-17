import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/auth";
import ProductLogo from "../components/ProductLogo";
import { useAuthStore } from "../store/auth";

export default function LoginView() {
  const navigate = useNavigate();
  const { login: setAuth } = useAuthStore();
  const [email, setEmail] = useState("admin");
  const [password, setPassword] = useState("1234");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await login(email, password);
      setAuth(result.access_token, result.user);
      navigate("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="loginPage">
      <section className="loginPanel" aria-label="Authentication">
        <div className="loginBrand">
          <ProductLogo />
          <h1>Pypmis AI SaaS</h1>
          <p>Project Controls, AWP and decision flow in one workspace.</p>
        </div>

        <form className="loginForm" onSubmit={handleSubmit}>
          {error && (
            <div className="loginError" role="alert">
              {error}
            </div>
          )}
          <div className="fieldStack">
            <label htmlFor="email">User</label>
            <input
              id="email"
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="fieldStack">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button className="loginSubmit" type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
