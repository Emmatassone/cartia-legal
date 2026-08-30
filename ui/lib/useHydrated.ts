"use client";

import { useSyncExternalStore } from "react";

import { useAuth } from "./auth";

const subscribe = (onChange: () => void) => useAuth.persist.onFinishHydration(onChange);
const getClientSnapshot = () => useAuth.persist.hasHydrated();
const getServerSnapshot = () => false;

/**
 * Indica si el store de auth ya leyó localStorage.
 *
 * Hace falta porque el primer render (server y cliente) no tiene el token todavía: sin
 * esperar la hidratación, la app parpadea mostrando el login a un usuario ya logueado.
 * Se resuelve con `useSyncExternalStore` en lugar de un `useEffect` con `setState` para no
 * disparar un render en cascada en cada montaje.
 */
export function useAuthHydrated(): boolean {
  return useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
}
