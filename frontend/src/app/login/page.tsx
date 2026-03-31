"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Lock, Mail, ArrowRight } from "lucide-react";
import { api, setToken } from "@/lib/api";
import type { LoginResponse } from "@/types";

export default function LoginPage() {
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
      const res = await api.post<LoginResponse>("/auth/login", {
        email,
        password,
      });
      setToken(res.access_token);
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* Left: Brand Panel */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden">
        <div className="absolute inset-0 gold-gradient opacity-90" />
        <div className="absolute inset-0 bg-gradient-to-br from-black/20 to-transparent" />
        <div className="relative z-10 flex flex-col justify-center px-16">
          <h1 className="text-5xl font-bold text-white mb-4">
            Vyapaar<span className="text-black/70">Bandhu</span>
          </h1>
          <p className="text-xl text-white/80 mb-8 max-w-md">
            India&apos;s smartest GST compliance platform for Chartered
            Accountants
          </p>
          <div className="space-y-4">
            {[
              "WhatsApp-first invoice collection",
              "AI-powered OCR + classification",
              "One-click GSTR-3B filing",
            ].map((feature, i) => (
              <div
                key={i}
                className="flex items-center gap-3 text-white/90"
                style={{ animationDelay: `${i * 150}ms` }}
              >
                <div className="w-2 h-2 rounded-full bg-white" />
                <span className="text-lg">{feature}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right: Login Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-bg-primary">
        <div className="w-full max-w-md animate-fade-in-up">
          <div className="lg:hidden mb-8">
            <h1 className="text-3xl font-bold">
              <span className="gold-text">Vyapaar</span>Bandhu
            </h1>
          </div>

          <h2 className="text-2xl font-semibold mb-2">Welcome back</h2>
          <p className="text-white/50 mb-8">
            Sign in to your CA dashboard
          </p>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm text-white/60 mb-2">
                Email
              </label>
              <div className="relative">
                <Mail
                  size={18}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30"
                />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="ca@example.com"
                  className="w-full pl-10 pr-4 py-3 bg-bg-surface border border-white/10 rounded-lg text-white placeholder:text-white/30 focus:outline-none focus:border-gold/50 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-white/60 mb-2">
                Password
              </label>
              <div className="relative">
                <Lock
                  size={18}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30"
                />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="w-full pl-10 pr-4 py-3 bg-bg-surface border border-white/10 rounded-lg text-white placeholder:text-white/30 focus:outline-none focus:border-gold/50 transition-colors"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 gold-gradient rounded-lg text-black font-semibold flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-black/30 border-t-black rounded-full animate-spin" />
              ) : (
                <>
                  Sign In <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
