import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Finitii",
  description: "AI-driven personal finance",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased bg-gray-50 text-gray-900 min-h-screen">
        {children}
      </body>
    </html>
  );
}
