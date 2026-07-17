import { notFound } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { companies, audits, proposals } from "@/db/schema";
import { generateProposal } from "@/lib/proposal";
import { faNum } from "@/lib/utils";
import { PrintActions } from "./print-button";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export default async function ProposalPrintPage({ params }: Params) {
  const { id } = await params;
  const companyId = Number(id);
  if (!Number.isFinite(companyId)) notFound();

  const rows = await db
    .select({ company: companies, audit: audits, proposal: proposals })
    .from(companies)
    .leftJoin(audits, eq(audits.companyId, companyId))
    .leftJoin(proposals, eq(proposals.companyId, companyId))
    .where(eq(companies.id, companyId))
    .limit(1);

  const row = rows[0];
  if (!row || !row.proposal) notFound();
  // Backfill pricing for proposals created before the pricing engine
  if (row.proposal.pricing.length === 0) {
    const regenerated = generateProposal(row.company, row.audit, row.proposal.keywords);
    const [updated] = await db
      .update(proposals)
      .set(regenerated)
      .where(eq(proposals.id, row.proposal.id))
      .returning();
    row.proposal = updated;
  }
  const { company, audit, proposal } = row;

  const today = new Date().toLocaleDateString("fa-IR", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="min-h-screen bg-[#0b0e12] py-10">
      <PrintActions />
      <div className="print-page mx-auto max-w-3xl rounded-3xl bg-white p-10 text-zinc-900 shadow-2xl sm:p-14">
        {/* Letterhead */}
        <div className="flex items-start justify-between border-b-4 border-emerald-500 pb-6">
          <div>
            <p className="text-xs font-bold tracking-widest text-emerald-600">
              پیشنهادنامه همکاری — خدمات سئو و بهینه‌سازی گوگل
            </p>
            <h1 className="mt-3 text-3xl font-black leading-snug">
              طرح رسیدن به صفحه اول گوگل
              <br />
              <span className="text-emerald-600">ویژه {company.name}</span>
            </h1>
          </div>
          <div className="text-left text-xs leading-6 text-zinc-500">
            <p className="font-black text-emerald-600">لیدفِر | LeadFair</p>
            <p>{today}</p>
            <p>شماره سند: {faNum(proposal.id)}-{faNum(company.id)}</p>
          </div>
        </div>

        {/* Meta */}
        <div className="mt-6 grid grid-cols-2 gap-3 rounded-2xl bg-emerald-50 p-5 text-sm sm:grid-cols-4">
          <div>
            <p className="text-[10px] font-bold text-zinc-500">رتبه فعلی در گوگل</p>
            <p className="mt-1 font-black text-rose-600">
              {company.googleRank ? faNum(company.googleRank) : "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-bold text-zinc-500">صفحه اول گوگل</p>
            <p className="mt-1 font-black text-rose-600">
              {company.onFirstPage ? "بله" : "خیر"}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-bold text-zinc-500">امتیاز سلامت وب‌سایت</p>
            <p className="mt-1 font-black text-amber-600">
              {audit ? `${faNum(audit.score)} از ۱۰۰` : "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-bold text-zinc-500">اولویت اقدام</p>
            <p className="mt-1 font-black text-emerald-700">{proposal.grade}</p>
          </div>
        </div>

        {/* Summary */}
        <p className="mt-8 rounded-2xl border-r-4 border-emerald-500 bg-zinc-50 p-5 text-sm leading-8 text-zinc-800">
          {proposal.summary}
        </p>

        {/* Sections */}
        <div className="mt-10 space-y-9">
          {proposal.sections.map((s) => (
            <section key={s.heading}>
              <h2 className="flex items-center gap-2 text-lg font-black text-zinc-900">
                <span className="h-5 w-1.5 rounded-full bg-emerald-500" />
                {s.heading}
              </h2>
              <p className="mt-3 text-sm leading-8 text-zinc-700">{s.body}</p>
              {s.bullets && (
                <ul className="mt-3 space-y-2">
                  {s.bullets.map((b, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 rounded-xl bg-zinc-50 px-4 py-2.5 text-sm leading-7 text-zinc-800"
                    >
                      <span className="mt-3 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                      {b}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>

        {/* Keywords */}
        <div className="mt-10 rounded-2xl border border-dashed border-emerald-300 bg-emerald-50/60 p-5">
          <p className="text-xs font-black text-emerald-700">کلمات کلیدی هدف این طرح</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {proposal.keywords.map((k) => (
              <span
                key={k}
                className="rounded-full bg-white px-3 py-1.5 text-xs font-bold text-emerald-800 ring-1 ring-emerald-200"
              >
                {k}
              </span>
            ))}
          </div>
        </div>

        {/* -------- 6. Pricing table -------- */}
        {proposal.pricing.length > 0 && (
          <section className="mt-12 break-inside-avoid-page">
            <h2 className="flex items-center gap-2 text-lg font-black text-zinc-900">
              <span className="h-5 w-1.5 rounded-full bg-amber-500" />
              ۶. ساختار پکیج سئو و برآورد شفاف هزینه
            </h2>
            <p className="mt-2 text-xs leading-6 text-zinc-500">
              {faNum(proposal.pricing.length)} بخش خدماتی با جزئیات کار و بازه هزینه واقعی بازار
              (تومان) — امکان انتخاب تک‌آیتمی یا اجرای کامل پکیج:
            </p>
            <table className="mt-4 w-full border-collapse overflow-hidden rounded-2xl text-sm">
              <thead>
                <tr className="bg-zinc-900 text-white">
                  <th className="px-4 py-3 text-right text-xs font-black">#</th>
                  <th className="px-4 py-3 text-right text-xs font-black">بخش خدماتی</th>
                  <th className="px-4 py-3 text-right text-xs font-black">شامل</th>
                  <th className="px-4 py-3 text-left text-xs font-black">هزینه (تومان)</th>
                </tr>
              </thead>
              <tbody>
                {proposal.pricing.map((p, i) => (
                  <tr key={p.title} className={i % 2 === 0 ? "bg-zinc-50" : "bg-white"}>
                    <td className="border border-zinc-200 px-4 py-3 font-black text-amber-600">
                      {faNum(i + 1)}
                    </td>
                    <td className="border border-zinc-200 px-4 py-3 font-extrabold leading-6">
                      {p.title}
                    </td>
                    <td className="border border-zinc-200 px-4 py-3 text-xs leading-6 text-zinc-600">
                      {p.details}
                    </td>
                    <td className="border border-zinc-200 px-4 py-3 text-left text-xs font-black tabular-nums text-zinc-800">
                      {faNum(p.costMin)}
                      <span className="mx-1 text-zinc-400">تا</span>
                      {faNum(p.costMax)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-emerald-600 text-white">
                  <td colSpan={3} className="px-4 py-3.5 text-sm font-black">
                    جمع سرمایه‌گذاری پکیج کامل
                  </td>
                  <td className="px-4 py-3.5 text-left text-sm font-black tabular-nums">
                    {faNum(proposal.totalMin ?? 0)} تا {faNum(proposal.totalMax ?? 0)}
                  </td>
                </tr>
              </tfoot>
            </table>
            <p className="mt-2 text-[10px] leading-5 text-zinc-400">
              پرداخت اقساطی ۳ ماهه امکان‌پذیر است. قیمت‌ها تا ۱۴ روز معتبرند و بیشترین بازگشت سرمایه
              با اجرای هماهنگ تمام بخش‌ها حاصل می‌شود.
            </p>
          </section>
        )}

        {/* -------- 7. Google penalty blacklist -------- */}
        {proposal.penalties.length > 0 && (
          <section className="mt-12 break-inside-avoid-page">
            <h2 className="flex items-center gap-2 text-lg font-black text-zinc-900">
              <span className="h-5 w-1.5 rounded-full bg-rose-500" />
              ۷. خط قرمزهای گوگل — کارهایی که هرگز انجام نمی‌دهیم
            </h2>
            <p className="mt-2 text-xs leading-6 text-zinc-500">
              روش‌های زیر «سئو کلاه‌سیاه» هستند. اگر هر مجری دیگری این‌ها را به شما پیشنهاد داد، بدانید
              که دارایی دیجیتال‌تان را در معرض پنالتی و حذف دائمی از گوگل قرار می‌دهد:
            </p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {proposal.penalties.map((pen) => (
                <div
                  key={pen.title}
                  className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3"
                >
                  <p className="text-[12px] font-extrabold text-rose-800">{pen.title}</p>
                  <p className="mt-1 text-[10px] leading-5 text-rose-600">
                    پیامد: {pen.consequence}
                  </p>
                </div>
              ))}
            </div>
            <p className="mt-3 rounded-xl bg-emerald-50 px-4 py-3 text-xs font-bold leading-6 text-emerald-800 ring-1 ring-emerald-200">
              تعهد کتبی: تمام خدمات این پیشنهادنامه صددرصد وایت‌هت و منطبق بر دستورالعمل‌های رسمی
              گوگل است؛ هرگونه افت رتبه ناشی از پنالتی، مسئولیت اجرایی تیم ماست.
            </p>
          </section>
        )}

        {/* CTA */}
        <div className="mt-10 rounded-2xl bg-zinc-900 p-7 text-white">
          <h2 className="text-lg font-black">گام بعدی — شروع همکاری</h2>
          <p className="mt-2 text-sm leading-8 text-zinc-300">
            این پیشنهادنامه بر اساس داده‌های واقعی حضور آنلاین {company.name} تهیه شده و تا ۱۴ روز
            معتبر است. برای شروع فاز اول و رزرو ظرفیت تیم اجرایی، همین هفته با ما تماس بگیرید —
            جلسه اول تحلیل رقبا <span className="font-black text-emerald-400">رایگان</span> است و
            پشت سر گذاشتن رقبا از همین‌جا آغاز می‌شود.
          </p>
          <div className="mt-4 flex flex-wrap gap-3 text-xs font-bold text-emerald-300">
            <span className="rounded-full bg-white/10 px-4 py-2">پاسخ‌گویی در کمتر از ۲۴ ساعت</span>
            <span className="rounded-full bg-white/10 px-4 py-2">گزارش شفاف هفتگی</span>
            <span className="rounded-full bg-white/10 px-4 py-2">بدون قرارداد بلندمدت اجباری</span>
          </div>
        </div>

        <p className="mt-8 text-center text-[10px] text-zinc-400">
          این سند به‌صورت خودکار توسط پلتفرم لیدفِر — اتوماسیون تحلیل لیدهای نمایشگاهی — تولید شده است.
        </p>
      </div>
    </div>
  );
}
