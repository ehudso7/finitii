"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken, isApiError } from "@/lib/api";
import { TID } from "@/lib/testids";
import { ErrorBox } from "@/components/ErrorBox";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setRequestId(null);
    setLoading(true);
    try {
      await api.post("/auth/register", { email, password });
      // Auto-login after register
      const { data } = await api.post("/auth/login", { email, password });
      setToken(data.token);
      router.push("/onboarding");
    } catch (err) {
      if (isApiError(err)) {
        setError(err.message);
        setRequestId(err.requestId);
      } else {
        setError(err instanceof Error ? err.message : "An unexpected error occurred");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="w-full max-w-md p-8 bg-white rounded shadow">
        <h1 className="text-2xl font-bold mb-6">Register</h1>
        <ErrorBox message={error} requestId={requestId} />
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            data-testid={TID.authEmail}
            name="email"
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full border rounded p-2"
          />
          <input
            data-testid={TID.authPassword}
            name="password"
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            className="w-full border rounded p-2"
          />
          <button
            data-testid={TID.authSubmit}
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white rounded p-2 hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Registering..." : "Register"}
          </button>
        </form>
        <p className="mt-4 text-sm text-center">
          Already have an account?{" "}
          <Link href="/login" data-testid={TID.authToLogin} className="text-blue-600 underline">
            Login
          </Link>
        </p>
      </div>
    </div>
  );
}
