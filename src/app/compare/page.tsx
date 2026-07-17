import { MarketCompare } from "@/components/market-compare";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "نبرد صفحه اول گوگل — لیدفِر",
  description: "مقایسه ۱۰ شرکت برتر صفحه اول گوگل با شرکت‌های نمایشگاهی و صدور پیشنهاد سئو",
};

export default function ComparePage() {
  return <MarketCompare />;
}
