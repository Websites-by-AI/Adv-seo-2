import type { Audit, PenaltyItem, PricingItem } from "@/db/schema";

/**
 * SEO package pricing engine — amounts in Toman, tuned to the Iranian
 * market (1404). Severity grade scales the workload:
 *  A = heavy rebuild / no site, B = mid, C = light optimization.
 */
export function buildPricing(
  grade: "A" | "B" | "C",
  audit: Audit | null,
): { items: PricingItem[]; totalMin: number; totalMax: number } {
  const f = grade === "A" ? 1.3 : grade === "C" ? 0.75 : 1;
  const scale = (min: number, max: number): [number, number] => [
    Math.round((min * f) / 500_000) * 500_000,
    Math.round((max * f) / 500_000) * 500_000,
  ];
  const item = (title: string, details: string, min: number, max: number): PricingItem => {
    const [costMin, costMax] = scale(min, max);
    return { title, details, costMin, costMax };
  };

  const needsSite =
    !audit ||
    audit.mode === "no-site" ||
    audit.mode === "unreachable" ||
    (audit.mode === "live" && audit.score < 35);

  const items: PricingItem[] = [
    item(
      "استراتژی و تحلیل عمیق رقبا",
      "تحلیل ۵ رقیب صفحه اول، استخراج ۳۰ کلمه کلیدی هدف و ترسیم نقشه راه ۹۰ روزه",
      4_000_000,
      7_000_000,
    ),
    item(
      "بهینه‌سازی فنی و سرعت سایت",
      "حدود ۲۰ ساعت کار متخصص فنی (نرخ ساعتی ۴۰۰ تا ۷۰۰ هزار تومان): رفع خطاها، Core Web Vitals و موبایل",
      8_000_000,
      14_000_000,
    ),
    item(
      "بهینه‌سازی داخلی صفحات (On-Page)",
      "بازنویسی Title و Meta تمام صفحات کلیدی، اصلاح ساختار H1 تا H3 و لینک‌سازی داخلی",
      5_000_000,
      8_000_000,
    ),
    item(
      "تولید محتوای تخصصی سئومحور",
      "۱۴ محتوای تخصصی حوزه شما (هر محتوا ۵۰۰ تا ۸۵۰ هزار تومان) همراه با تصویرسازی و بهینه‌سازی",
      7_000_000,
      12_000_000,
    ),
    item(
      "لینک‌سازی از ده سایت برتر صنعت",
      "رپورتاژ آگهی و بک‌لینک دائمی در ۵ سایت از ۱۰ سایت برتر همین صنعت (هر رپورتاژ ۲ تا ۴ میلیون تومان)",
      12_000_000,
      20_000_000,
    ),
    item(
      "اسکیما و داده ساختاریافته",
      "پیاده‌سازی Schema‌های Organization، Product و FAQ برای تصاحب جایگاه صفر و ریچ‌اسنیپت",
      2_500_000,
      4_000_000,
    ),
    item(
      "سئوی محلی و گوگل بیزینس پروفایل",
      "ثبت و بهینه‌سازی پروفایل گوگل مپ، مدیریت نظرات و ورود به پک محلی نتایج تهران",
      3_000_000,
      5_000_000,
    ),
    needsSite
      ? item(
          "طراحی / بازطراحی کامل وب‌سایت",
          audit?.mode === "no-site"
            ? "طراحی سایت شرکتی ۸ تا ۱۲ صفحه: ریسپانسیو، پرسرعت، پنل مدیریت فارسی و آماده سئو از روز اول"
            : "بازطراحی زیرساخت سایت فعلی روی چارچوب مدرن با مهاجرت بدون افت رتبه",
          30_000_000,
          55_000_000,
        )
      : item(
          "مشاوره و آموزش تیم داخلی شما",
          "۶ ساعت جلسه تخصصی با تیم شما برای نگهداری رتبه و تولید محتوای درون‌سازمانی",
          3_000_000,
          5_000_000,
        ),
    item(
      "بهینه‌سازی نرخ تبدیل (CRO)",
      "طراحی مسیر تماس، فرم‌های هوشمند و دکمه‌های پاسخ‌گو تا بازدید گوگل، تبدیل به تماس و فروش شود",
      4_000_000,
      6_000_000,
    ),
    item(
      "پایش، گزارش هفتگی و مانیتورینگ",
      "مانیتورینگ روزانه رتبه‌ها، گزارش شفاف هفتگی و جلسه ماهانه (ماهی ۲ تا ۳ میلیون تومان)",
      6_000_000,
      9_000_000,
    ),
  ];

  return {
    items,
    totalMin: items.reduce((s, i) => s + i.costMin, 0),
    totalMax: items.reduce((s, i) => s + i.costMax, 0),
  };
}

/** Black-hat tactics that Google penalizes — the "never do this" list. */
export const PENALTY_LIST: PenaltyItem[] = [
  {
    title: "خرید انبوه بک‌لینک اسپم و شبکه‌های PBN",
    consequence: "پنالتی دستی گوگل و حذف کامل سایت از نتایج جستجو",
  },
  {
    title: "بمباران کلمه کلیدی (Keyword Stuffing)",
    consequence: "افت شدید رتبه توسط الگوریتم‌های ضداسپم محتوایی",
  },
  {
    title: "کلاکینگ؛ نمایش محتوای متفاوت به گوگل و کاربر",
    consequence: "دی‌ایندکس شدن دائمی دامنه بدون هشدار قبلی",
  },
  {
    title: "متن و لینک مخفی (هم‌رنگ پس‌زمینه یا فونت صفر)",
    consequence: "تشخیص خودکار توسط کراولر و پنالتی الگوریتمی",
  },
  {
    title: "کپی محتوای رقبا و محتوای تکراری",
    consequence: "نادیده گرفته شدن صفحات و خروج آرام از نتایج",
  },
  {
    title: "کلیک مصنوعی، ربات جستجو و سئو کلاه‌خاکستری ترافیکی",
    consequence: "شناسایی الگوی غیرطبیعی و سقوط ناگهانی همه رتبه‌ها",
  },
  {
    title: "ریدایرکت توده‌ای دامنه‌های تازه‌انقضا برای تزریق اعتبار",
    consequence: "بی‌اثر شدن لینک‌ها و احتمال پنالتی دستی",
  },
  {
    title: "اسکیمای تقلبی و نمایش امتیاز/ریویو جعلی در نتایج",
    consequence: "حذف ریچ‌ریزالت و جریمه اعتبار دامنه",
  },
  {
    title: "کامنت‌اسپم و لینک‌فارم‌های خودکار",
    consequence: "کاهش اعتبار دامنه (Domain Trust) و فیلتر لینک‌ها",
  },
];
