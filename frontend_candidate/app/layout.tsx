import type { Metadata } from "next";
import { Space_Grotesk, Inter } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/layout/AppShell";
import { UserModeProvider } from "@/lib/context";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
});
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "ORCA — Marine Intelligence & Autonomous AI Platform",
  description: "Safety-first marine decision support powered by collaborative AI agents",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${spaceGrotesk.variable} ${inter.variable} font-body bg-bg text-text-primary antialiased selection:bg-cyan/20 selection:text-cyan`}>
        <UserModeProvider>
          <AppShell>{children}</AppShell>
        </UserModeProvider>
      </body>
    </html>
  );
}