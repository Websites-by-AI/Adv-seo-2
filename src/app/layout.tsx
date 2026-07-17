import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Vazirmatn } from "next/font/google";
import "./globals.css";

const vazir = Vazirmatn({
  subsets: ["arabic", "latin"],
  variable: "--font-vazir",
  display: "swap",
});

export const metadata: Metadata = {
  title: "لیدفِر — اتوماسیون شکار لید نمایشگاهی و پیشنهاد سئو",
  description:
    "از لیست شرکت‌های نمایشگاه تا پیشنهادنامه آماده سئو؛ شرکت‌هایی که در صفحه اول گوگل نیستند را شکار کنید و پیشنهاد رسیدن به تاپ ۱۰ بدهید.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className={vazir.variable}>
      <body className="min-h-screen bg-[#070a0e] text-zinc-100 antialiased">
        {children}
      </body>
    </html>
  );
}
