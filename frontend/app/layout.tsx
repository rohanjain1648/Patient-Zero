import "./globals.css";
import type { ReactNode } from "react";

export const metadata = { title: "Patient Zero", description: "Trace where a claim started and who really corroborates it" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
