"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

import { Logo } from "./Logo";

type Mode = "login" | "signup";

const FIELD_CLASS =
  "w-full rounded-lg border border-ink-700 bg-ink-900 px-3 py-2.5 text-sm text-ink-100 " +
  "placeholder:text-ink-500 focus:border-brass-500 focus:outline-none";

export function AuthScreen() {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [estudio, setEstudio] = useState("");
  const [matricula, setMatricula] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const setTokens = useAuth((state) => state.setTokens);
  const queryClient = useQueryClient();

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const tokens =
        mode === "login"
          ? await api.login({ email, password })
          : await api.signup({
              email,
              password,
              full_name: fullName,
              estudio: estudio || undefined,
              matricula: matricula || undefined,
            });
      setTokens(tokens);
      // Los datos del usuario y las conversaciones los trae TanStack Query en cuanto el
      // token está en el store; solo hay que invalidar lo que quedó cacheado como vacío.
      await queryClient.invalidateQueries();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No se pudo completar la operación");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-7 text-center">
          <Logo className="text-2xl" />
          <p className="mt-3 text-sm leading-relaxed text-ink-400">
            Investigación jurídica asistida sobre normativa, jurisprudencia y doctrina
            argentina.
          </p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3">
          {mode === "signup" && (
            <>
              <input
                className={FIELD_CLASS}
                placeholder="Nombre y apellido"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                required
                minLength={2}
                autoComplete="name"
              />
              <input
                className={FIELD_CLASS}
                placeholder="Estudio (opcional)"
                value={estudio}
                onChange={(event) => setEstudio(event.target.value)}
                autoComplete="organization"
              />
              <input
                className={FIELD_CLASS}
                placeholder="Matrícula (opcional)"
                value={matricula}
                onChange={(event) => setMatricula(event.target.value)}
              />
            </>
          )}

          <input
            className={FIELD_CLASS}
            type="email"
            placeholder="Email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoComplete="email"
          />
          <input
            className={FIELD_CLASS}
            type="password"
            placeholder={mode === "signup" ? "Contraseña (mínimo 10 caracteres)" : "Contraseña"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={mode === "signup" ? 10 : undefined}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
          />

          {error && (
            <p className="text-sm text-red-400" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="mt-1 flex items-center justify-center gap-2 rounded-lg bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-60"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {mode === "login" ? "Ingresar" : "Crear cuenta"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-ink-400">
          {mode === "login" ? "¿Todavía no tenés cuenta?" : "¿Ya tenés cuenta?"}{" "}
          <button
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setError(null);
            }}
            className="text-brass-300 underline underline-offset-2 hover:text-brass-400"
          >
            {mode === "login" ? "Registrate" : "Ingresá"}
          </button>
        </p>
      </div>
    </main>
  );
}
