import type { Metadata } from "next";
import "./styles.css";
import "./logo.css";
import "./purchase.css";
import "./dashboard.css";

export const metadata: Metadata = { title: "OrvexaDB", description: "Inventario PostgreSQL para equipos", icons: { icon: "/orvexa-logo.png" } };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
