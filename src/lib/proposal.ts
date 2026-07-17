import type { Audit, Company, PenaltyItem, PricingItem, ProposalSection } from "@/db/schema";
import { faNum } from "./utils";
import { buildPricing, PENALTY_LIST } from "./pricing";

export interface GeneratedProposal {
  keyword: string;
  grade: "A" | "B" | "C";
  summary: string;
  keywords: string[];
  sections: ProposalSection[];
  pricing: PricingItem[];
  penalties: PenaltyItem[];
  totalMin: number;
  totalMax: number;
}

/** Build a complete, ready-to-send Persian SEO proposal. */
export function generateProposal(
  company: Company,
  audit: Audit | null,
  keywords: string[],
): GeneratedProposal {
  const rank = company.googleRank;
  const rankText =
    rank === null || rank === undefined
      ? "مشخص نیست"
      : rank > 100
        ? "خارج از ۱۰۰ نتیجه اول"
        : `رتبه ${faNum(rank)}`;
  const score = audit?.score ?? 0;

  const grade: "A" | "B" | "C" =
    audit?.mode === "no-site" || (rank !== null && rank !== undefined && rank > 50)
      ? "A"
      : score < 55
        ? "B"
        : "C";

  const timeline =
    grade === "A" ? "۴ تا ۶ ماه" : grade === "B" ? "۳ تا ۵ ماه" : "۲ تا ۴ ماه";

  const summary =
    audit?.mode === "no-site"
      ? `${company.name} در حال حاضر وب‌سایت اختصاصی ندارد و در نتایج جستجوی گوگل (رتبه فعلی: ${rankText}) برای مشتریان آنلاین نامرئی است. با راه‌اندازی یک وب‌سایت استاندارد و اجرای برنامه سئوی اختصاصی، این برند می‌تواند ظرف ${timeline} به صفحه اول گوگل برای کلمات کلیدی حوزه فعالیت خود برسد و سهم بازار دیجیتال رقبا را پس بگیرد.`
      : `وب‌سایت فعلی ${company.name} با امتیاز فنی ${faNum(score)} از ۱۰۰ و حضور در ${rankText} گوگل، عملاً بخش بزرگی از مشتریان آنلاین را به رقبا واگذار می‌کند. تیم ما با اصلاح زیرساخت فنی، بازطراحی معماری محتوا و لینک‌سازی هدفمند، مسیر رسیدن به ۱۰ نتیجه اول گوگل را در ${timeline} تضمین‌محور اجرا می‌کند.`;

  const currentStatusBullets: string[] = [
    `کلمه کلیدی بررسی‌شده: «${company.name}»`,
    `وضعیت فعلی در گوگل: ${rankText}${company.rankMode === "simulated" ? " (برآورد خودکار)" : ""}`,
    `صفحه اول گوگل: ${company.onFirstPage ? "بله — در حال حاضر دیده می‌شود" : "خیر — خارج از ۱۰ نتیجه اول"}`,
  ];
  if (audit) {
    if (audit.mode === "no-site") currentStatusBullets.push("وب‌سایت اختصاصی: یافت نشد");
    else currentStatusBullets.push(`وب‌سایت: ${audit.url ?? "—"}`);
    if (audit.httpStatus) currentStatusBullets.push(`کد پاسخ سرور: ${faNum(audit.httpStatus)}`);
    if (audit.loadTimeMs)
      currentStatusBullets.push(`سرعت بارگذاری: ${(audit.loadTimeMs / 1000).toFixed(1)} ثانیه`);
  }

  const issueBullets =
    audit && audit.issues.length > 0
      ? audit.issues
      : [" تحلیل تکمیلی پس از اتصال به وب‌سایت انجام می‌شود"];

  const sections: ProposalSection[] = [
    {
      heading: "۱. وضعیت فعلی شما در گوگل",
      body: `تیم تحلیل ما حضور دیجیتال ${company.name} را پس از نمایشگاه بررسی کرد. نتایج این بررسی نشان می‌دهد سهم فعلی شما از جستجوهای پرتکرار حوزه کاری‌تان نزدیک به صفر است:`,
      bullets: currentStatusBullets,
    },
    {
      heading: "۲. مشکلات کلیدی شناسایی‌شده",
      body:
        audit?.mode === "no-site"
          ? "بزرگ‌ترین چالش، نبود زیرساخت دیجیتال است؛ در شرایطی که بیش از ۷۰٪ خریداران صنعتی پیش از تماس، برند شما را در گوگل جستجو می‌کنند:"
          : `امتیاز سلامت سئوی وب‌سایت شما ${faNum(score)} از ۱۰۰ است. مهم‌ترین موانعی که امروز جلوی رتبه گرفتن شما را گرفته‌اند:`,
      bullets: issueBullets,
    },
    {
      heading: "۳. برنامه اقدام ۹۰ روزه ما برای رسیدن به صفحه اول",
      body: "مسیر شفاف سه فازی که برای برند شما طراحی کرده‌ایم:",
      bullets: [
        "فاز ۱ (روز ۱ تا ۳۰) — زیرساخت فنی: رفع خطاهای سرچ کنسول، بهینه‌سازی سرعت و Core Web Vitals، فعال‌سازی HTTPS کامل، پیاده‌سازی اسکیمای Organization/Product/FAQ و ثبت گوگل بیزینس پروفایل",
        "فاز ۲ (روز ۳۰ تا ۶۰) — معماری محتوا: تولید ۱۲ تا ۱۶ محتوای هدفمند بر اساس کلمات کلیدی پول‌ساز حوزه شما، بازنویسی تگ‌های Title و Description، ساخت صفحات فرود محصول و سؤالات متداول",
        "فاز ۳ (روز ۶۰ تا ۹۰) — اعتبارسازی: لینک‌سازی از رسانه‌ها و دایرکتوری‌های معتبر صنعتی، رپورتاژ هدفمند، فعال‌سازی شبکه‌های اجتماعی متصل به سایت و پایش هفتگی رتبه‌ها",
        audit?.mode === "no-site"
          ? "ویژه شما: طراحی و راه‌اندازی وب‌سایت شرکتی سئومحور (ریسپانسیو، سریع و آماده تبلیغات) در هفته اول همکاری"
          : "ویژه شما: بازطراحی صفحات کلیدی برای افزایش نرخ تبدیل بازدیدکننده به تماس",
      ],
    },
    {
      heading: "۴. کلمات کلیدی پیشنهادی برای تصاحب صفحه اول",
      body: "این عبارت‌ها همین حالا توسط مشتریان بالفعل شما جستجو می‌شوند و رقبایتان از آن‌ها غافل‌اند:",
      bullets: keywords.map((k) => `«${k}»`),
    },
    {
      heading: "۵. چرا الان؟ فرصت پس از نمایشگاه",
      body: "هفته‌های پس از نمایشگاه، دقیقاً زمانی است که نام برند شما بیشترین جستجو را دارد. بازدیدکنندگان غرفه شما برای ادامه مذاکره ابتدا در گوگل سرچ می‌کنند؛ اگر شما را نیابند، با اطلاعات تماس رقیب مواجه می‌شوند. هر ماه تأخیر، یعنی تحویل لیدهای گرم نمایشگاهی به رقبایی که همین حالا روی سئو سرمایه‌گذاری کرده‌اند.",
      bullets: [
        `برآورد رسیدن به صفحه اول گوگل: ${timeline}`,
        "گزارش شفاف هفتگی از رتبه، ترافیک و تماس‌های ورودی",
        "بدون قرارداد بلندمدت اجباری — خروج هر زمان با تحویل کامل دارایی‌ها",
      ],
    },
  ];

  const { items, totalMin, totalMax } = buildPricing(grade, audit);

  return {
    keyword: company.name,
    grade,
    summary,
    keywords,
    sections,
    pricing: items,
    penalties: PENALTY_LIST,
    totalMin,
    totalMax,
  };
}
