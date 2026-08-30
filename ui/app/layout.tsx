import type { Metadata, Viewport } from "next";

import { Providers } from "@/components/Providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "CartIA Legal — Investigación jurídica asistida",
  description:
    "Asistente de investigación jurídica para abogados y estudios jurídicos de Argentina. " +
    "Respuestas fundadas en normativa, jurisprudencia y doctrina, con cita de fuentes.",
};

export const viewport: Viewport = {
  themeColor: "#070e1c",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-AR">
      <body className="h-full antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
