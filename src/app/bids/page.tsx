import { BidsMarket } from "@/components/bids-market";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "بازار مناقصه کور سئو — لیدفِر",
  description: "فراخوان محرمانه قیمت‌گذاری برای آژانس‌های سئو ایران و واگذاری لید پس از تسویه پورسانت",
};

export default function BidsPage() {
  return <BidsMarket />;
}
