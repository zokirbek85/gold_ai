"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authApi.register(email, password);
      const { data } = await authApi.login(email, password);
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      router.push("/dashboard");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4"
      style={{ background: "var(--bg)" }}
    >
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse 60% 40% at 50% 0%, rgba(245,166,35,0.06) 0%, transparent 70%)",
        }}
      />

      <div className="w-full max-w-[360px] relative z-10">
        <div className="text-center mb-8">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5 text-2xl font-bold"
            style={{
              background: "rgba(245,166,35,0.12)",
              color: "var(--gold)",
              border: "1px solid rgba(245,166,35,0.2)",
            }}
          >
            AU
          </div>
          <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--gold)" }}>GOLD AI</h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Create your account</p>
        </div>

        <div
          className="rounded-2xl p-6"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <h2 className="text-base font-semibold mb-5" style={{ color: "var(--text)" }}>Get started</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-muted)" }}>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" className="input" />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-muted)" }}>Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={6} placeholder="min. 6 characters" className="input" />
            </div>

            {error && (
              <div className="text-xs px-3 py-2.5 rounded-lg" style={{ background: "rgba(239,68,68,0.08)", color: "var(--red)", border: "1px solid rgba(239,68,68,0.2)" }}>
                {error}
              </div>
            )}

            <button type="submit" disabled={loading} className="btn btn-gold w-full justify-center py-2.5 text-sm mt-2">
              {loading ? "Creating account…" : "Create Account"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs mt-4" style={{ color: "var(--text-faint)" }}>
          Already have an account?{" "}
          <a href="/login" style={{ color: "var(--gold)" }} className="hover:underline">Sign in</a>
        </p>
      </div>
    </div>
  );
}
