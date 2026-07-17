import { notFound } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { agencies, bidRequests, companies, quotes } from "@/db/schema";
import { faNum } from "@/lib/utils";
import { BidQuoteForm } from "@/components/bid-widget-form";
import {
  Lock,
  MapPin,
  Factory,
  Search,
  Gauge,
  Bug,
  Users,
  Unlock,
  Phone,
  Globe,
} from "lucide-react";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ token: string }> };

/**
 * Public bidding widget — fully anonymized until commission settlement.
 * The client identity is NEVER rendered here before status === "revealed".
 */
export default async function BidWidgetPage({ params }: Params) {
  const { token } = await params;
  const [bid] = await db
    .select()
    .from(bidRequests)
    .where(eq(bidRequests.token, token))
    .limit(1);
  if (!bid) notFound();

  const agencyList = await db.select().from(agencies);
  const bidQuotes = await db.select().from(quotes).where(eq(quotes.bidId, bid.id));
  const snap = bid.snapshot;

  let reveal: { name: string; phone: string | null; website: string | null } | null = null;
  if (bid.status === "revealed") {
    const [company] = await db
      .select()
      .from(companies)
      .where(eq(companies.id, bid.companyId))
      .limit(1);
    if (company) reveal = { name: company.name, phone: company.phone, website: company.website };
  }

  return (
    <div className="min-h-screen bg-zinc-100 py-10 text-zinc-900">
      <div className="mx-auto max-w-3xl px-4">
        {/* Letterhead */}
        <div className="rounded-3xl bg-white p-8 shadow-xl sm:p-10">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b-4 border-zinc-900 pb-6">
            <div>
              <p className="flex items-center gap-1.5 text-xs font-black text-zinc-500">
                <Lock className="h-3.5 w-3.5" />
                فراخوان قیمت‌گذاری محرمانه — پلتفرم لیدفِر
              </p>
              <h1 className="mt-3 text-2xl font-black sm:text-3xl">{bid.alias}</h1>
            </div>
            <div className="rounded-2xl bg-zinc-900 px-5 py-3 text-center text-white">
              <p className="text-[10px] font-bold text-zinc-400">قیمت‌های ثبت‌شده</p>
              <p className="text-2xl font-black tabular-nums">{faNum(bidQuotes.length)}</p>
            </div>
          </div>

          {/* Confidentiality banner */}
          <div className="mt-5 flex items-start gap-3 rounded-2xl border border-dashed border-amber-300 bg-amber-50 px-5 py-4">
            <Lock className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <p className="text-xs font-bold leading-6 text-amber-800">
              هویت کارفرما طبق قوانین مناقصه کور محرمانه است و در هیچ بخشی از این سند نمایش داده
              نمی‌شود. پس از پذیرش قیمت برنده و تسویه پورسانت {faNum(bid.commissionPercent)}٪
              پلتفرم، اطلاعات کامل تماس کارفرما مستقیماً به آژانس برنده سپرده می‌شود.
            </p>
          </div>

          {/* Anonymized brief */}
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { icon: Factory, label: "صنعت", value: bid.industry },
              { icon: MapPin, label: "شهر", value: bid.city },
              {
                icon: Search,
                label: "رتبه فعلی در گوگل",
                value: snap.googleRank ? faNum(snap.googleRank) : "نامرئی",
              },
              {
                icon: Gauge,
                label: "امتیاز سلامت سایت",
                value: snap.score !== null ? `${faNum(snap.score)}/۱۰۰` : "—",
              },
            ].map((f) => (
              <div key={f.label} className="rounded-2xl bg-zinc-50 p-4">
                <f.icon className="h-4 w-4 text-zinc-400" />
                <p className="mt-2 text-[10px] font-bold text-zinc-400">{f.label}</p>
                <p className="mt-1 text-sm font-black leading-6">{f.value}</p>
              </div>
            ))}
          </div>

          {/* Reference package */}
          {snap.packageItems.length > 0 && (
            <div className="mt-8">
              <h2 className="flex items-center gap-2 text-base font-black">
                <Bug className="h-4 w-4 text-zinc-400" />
                محدوده کار پروژه — {faNum(snap.packageItems.length)} بخش خدماتی
              </h2>
              <p className="mt-1 text-xs text-zinc-500">
                پکیج مرجع طراحی‌شده توسط لیدفِر؛ قیمت نهایی با شماست — رقابتی قیمت بدهید:
              </p>
              <div className="mt-4 overflow-hidden rounded-2xl border border-zinc-200">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="bg-zinc-900 text-white">
                      <th className="px-4 py-2.5 text-right text-xs font-black">#</th>
                      <th className="px-4 py-2.5 text-right text-xs font-black">بخش خدماتی</th>
                      <th className="px-4 py-2.5 text-left text-xs font-black">بازه مرجع (تومان)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snap.packageItems.map((p, i) => (
                      <tr key={p.title} className={i % 2 === 0 ? "bg-zinc-50" : "bg-white"}>
                        <td className="border-t border-zinc-200 px-4 py-2.5 font-black text-zinc-400">
                          {faNum(i + 1)}
                        </td>
                        <td className="border-t border-zinc-200 px-4 py-2.5 text-xs font-extrabold leading-6">
                          {p.title}
                        </td>
                        <td className="border-t border-zinc-200 px-4 py-2.5 text-left text-xs font-bold tabular-nums text-zinc-600">
                          {faNum(p.costMin)} — {faNum(p.costMax)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-emerald-600 text-white">
                      <td colSpan={2} className="px-4 py-3 text-xs font-black">
                        جمع بازه مرجع پکیج کامل
                      </td>
                      <td className="px-4 py-3 text-left text-xs font-black tabular-nums">
                        {faNum(snap.totalMin)} — {faNum(snap.totalMax)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          )}

          {/* Revealed client data (post-commission) */}
          {reveal && (
            <div className="mt-8 rounded-2xl border-2 border-emerald-400 bg-emerald-50 p-6">
              <h2 className="flex items-center gap-2 text-base font-black text-emerald-800">
                <Unlock className="h-5 w-5" />
                اطلاعات کارفرما — آشکار شده پس از تسویه پورسانت
              </h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl bg-white p-4 ring-1 ring-emerald-200">
                  <p className="text-[10px] font-bold text-zinc-400">نام شرکت</p>
                  <p className="mt-1 text-sm font-black leading-6">{reveal.name}</p>
                </div>
                {reveal.phone && (
                  <div className="rounded-xl bg-white p-4 ring-1 ring-emerald-200">
                    <p className="flex items-center gap-1 text-[10px] font-bold text-zinc-400">
                      <Phone className="h-3 w-3" /> تلفن تماس
                    </p>
                    <p className="mt-1 text-sm font-black" dir="ltr">
                      {reveal.phone}
                    </p>
                  </div>
                )}
                {reveal.website && (
                  <div className="rounded-xl bg-white p-4 ring-1 ring-emerald-200">
                    <p className="flex items-center gap-1 text-[10px] font-bold text-zinc-400">
                      <Globe className="h-3 w-3" /> وب‌سایت
                    </p>
                    <a
                      href={reveal.website}
                      target="_blank"
                      rel="noreferrer"
                      dir="ltr"
                      className="mt-1 block truncate text-sm font-black text-emerald-700 underline"
                    >
                      {reveal.website}
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Quote form */}
        {bid.status === "open" ? (
          <div className="mt-6 rounded-3xl bg-white p-8 shadow-xl sm:p-10">
            <h2 className="flex items-center gap-2 text-lg font-black">
              <Users className="h-5 w-5 text-zinc-400" />
              ثبت قیمت پیشنهادی آژانس
            </h2>
            <p className="mt-1 mb-6 text-xs leading-6 text-zinc-500">
              بدون دانستن نام کارفرما، بر اساس محدوده کار بالا قیمت رقابتی خود را ثبت کنید. بهترین
              پیشنهاد (قیمت + سابقه + زمان‌بندی) انتخاب می‌شود.
            </p>
            <BidQuoteForm token={token} agencies={agencyList} />
          </div>
        ) : (
          <div className="mt-6 rounded-3xl border border-zinc-300 bg-white p-8 text-center shadow-xl">
            <p className="text-sm font-black text-zinc-600">
              این فراخوان بسته شده و قیمت برنده انتخاب و تسویه شده است.
            </p>
          </div>
        )}

        <p className="mt-6 text-center text-[10px] text-zinc-400">
          پلتفرم مناقصه کور سئو لیدفِر — محرمانگی کارفرما تا تسویه پورسانت تضمین‌شده است.
        </p>
      </div>
    </div>
  );
}
