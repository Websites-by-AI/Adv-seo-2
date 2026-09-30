// Turkey (Istanbul) procurement market — seeded deterministic data + scoring logic.
// Port of the Python module in server.py. Works WITHOUT a database: sample rows are
// educational (sample:true, fictional +90 contacts); ratings are kept in-memory only
// (per serverless isolate, ephemeral:true — they reset on redeploy).
import { createHash } from "crypto";

export interface Region { id: string; fa: string; tr: string; demand: number; note: string }
export interface Consumable { id: string; fa: string; consumption: number; margin: [number, number]; regulated: boolean; certNote?: string; keywords: string[] }
export interface Bid {
  id: string; market: string; clinic: string; need: string; regionId: string; regionTr: string;
  categoryId: string; categoryFa: string; quantity: number | null; budgetTry: number | null;
  deadline: string; contact: string; source: string; sample: boolean;
}
export interface SupplierProduct {
  categoryId: string; categoryFa: string; name: string; unit: string;
  priceTry: number; stock: number | null; minOrder: number; deliveryDays: number;
}
export interface Supplier {
  id: string; market: string; name: string; regionId: string; regionFa: string; regionTr: string;
  phone: string; deliveryZones: string[]; products: SupplierProduct[];
  sample: boolean; source: string;
}

export const CLINIC_REGIONS: Region[] = [
  { id: "sisli", fa: "شیشلی", tr: "Şişli", demand: 5, note: "قطب بیمارستان‌ها و کلینیک‌های خصوصی؛ قلب گردشگری سلامت" },
  { id: "kadikoy", fa: "کادیکوی", tr: "Kadıköy", demand: 4, note: "بخش آسیایی؛ تراکم بالای کلینیک‌های زیبایی و دندان‌پزشکی" },
  { id: "bakirkoy", fa: "باکیرکوی", tr: "Bakırköy", demand: 4, note: "قطب تکمیلی بیمارستانی؛ دسترسی فرودگاهی" },
  { id: "besiktas", fa: "بشیکتاش", tr: "Beşiktaş", demand: 4, note: "کلینیک‌های لاکچری و زیبایی" },
  { id: "atasehir", fa: "آتاشهیر", tr: "Ataşehir", demand: 4, note: "مرکز مالی آسیایی؛ کلینیک‌های تخصصی" },
  { id: "beyoglu", fa: "بی‌اوغلو", tr: "Beyoğlu", demand: 4, note: "تقسیم؛ گردشگران بین‌المللی زیبایی" },
  { id: "uskudar", fa: "اسکودار", tr: "Üsküdar", demand: 3, note: "مسکونی متراکم؛ درمانگاه‌های خانوادگی" },
  { id: "bahcelievler", fa: "باغچه‌لیلر", tr: "Bahçelievler", demand: 3, note: "کلینیک‌های عمومی و دندان" },
  { id: "fatih", fa: "فاتح", tr: "Fatih", demand: 3, note: "تاریخی؛ درمانگاه‌های قیمت‌مناسب و بلندمدت" },
  { id: "beylikduzu", fa: "بیلیک‌دوزو", tr: "Beylikdüzü", demand: 3, note: "رشد جمعیت جوان؛ کلینیک‌های نو" },
];

export const RESTAURANT_REGIONS: Region[] = [
  { id: "bagcilar", fa: "باغجیلار", tr: "Bağcılar", demand: 5, note: "متراکم‌ترین منطقه مسکونی؛ رستوران‌های محلی و بیرون‌بر فراوان" },
  { id: "esenler", fa: "اسنلر", tr: "Esenler", demand: 4, note: "تراکم بالای غذاخوری‌های قیمت‌مناسب و عبوری" },
  { id: "gungoren", fa: "گونگورن", tr: "Güngören", demand: 4, note: "بازار محلی پرتردد؛ تقاضای پایدار مواد اولیه" },
  { id: "kucukcekmece", fa: "کوچوک‌چکمجه", tr: "Küçükçekmece", demand: 4, note: "رشد جمعیت و رستوران‌های خانوادگی" },
  { id: "esenyurt", fa: "اسنیورت", tr: "Esenyurt", demand: 4, note: "حجم بالای بیرون‌بر؛ حساس به قیمت" },
  { id: "umraniye", fa: "عمرانیه", tr: "Ümraniye", demand: 4, note: "بخش آسیایی؛ رستوران‌های اداری و کارگری" },
  { id: "pendik", fa: "پندیک", tr: "Pendik", demand: 3, note: "کنار فرودگاه صبیحا؛ غذاخوری‌های ساحلی و عبوری" },
  { id: "kartal", fa: "کارتال", tr: "Kartal", demand: 3, note: "ساحل آسیایی؛ رستوران‌های ماهی و محلی" },
  { id: "sultanbeyli", fa: "سلطان‌بیلی", tr: "Sultanbeyli", demand: 3, note: "منطقه در حال رشد؛ قیمت‌محور" },
  { id: "gaziosmanpasa", fa: "غازی‌عثمان‌پاشا", tr: "Gaziosmanpaşa", demand: 3, note: "بازار سنتی و فروشگاه‌های مواد غذایی متمرکز" },
];

export const CLINIC_CONSUMABLES: Consumable[] = [
  { id: "exam-gloves", fa: "دستکش معاینه (نایتریل/لاتکس)", consumption: 5, margin: [5, 12], regulated: false, keywords: ["glove", "gloves", "دستکش", "eldiven"] },
  { id: "syringes-needles", fa: "سرنگ و سوزن", consumption: 5, margin: [6, 14], regulated: false, keywords: ["syringe", "needle", "سرنگ", "سوزن", "şırınga", "iğne"] },
  { id: "sterile-dressings", fa: "گاز استریل و پانسمان", consumption: 4, margin: [8, 16], regulated: false, keywords: ["gauze", "dressing", "bandage", "گاز", "پانسمان", "steril"] },
  { id: "masks-respirators", fa: "ماسک و تنفسی", consumption: 4, margin: [6, 12], regulated: false, keywords: ["mask", "maske", "ماسک", "respirator", "ffp"] },
  { id: "disinfectants", fa: "مواد ضدعفونی و سطوح", consumption: 4, margin: [10, 20], regulated: false, keywords: ["disinfect", "antiseptic", "dezenfektan", "ضدعفونی", "الکل"] },
  { id: "dental-composites", fa: "کامپوزیت و مواد دندانی", consumption: 3, margin: [15, 30], regulated: false, keywords: ["composite", "کامپوزیت", "dental", "دندان", "bonding"] },
  { id: "dental-implants", fa: "ایمپلنت دندانی", consumption: 3, margin: [20, 45], regulated: true, keywords: ["implant", "ایمپلنت", "abutment", "fixture", "فیکسچر"] },
  { id: "dermal-fillers", fa: "ژل و فیلر پوستی", consumption: 2, margin: [25, 50], regulated: true, keywords: ["filler", "فیلر", "ژل", "hyaluron", "هیالورونیک"] },
  { id: "botulinum-toxin", fa: "بوتولینوم (بوتاکس و مشابه)", consumption: 2, margin: [30, 55], regulated: true, keywords: ["botox", "بوتاکس", "toxin", "توكسین", "توکسین", "botulinum"] },
  { id: "pdo-threads", fa: "نخ لیفت PDO", consumption: 2, margin: [20, 40], regulated: true, keywords: ["thread", "pdo", "نخ", "لیفت", "cog"] },
  { id: "prp-microneedling", fa: "کیت PRP و میکرونیدلینگ", consumption: 2, margin: [25, 45], regulated: false, keywords: ["prp", "microneedle", "پی‌آر‌پی", "میکرونیدلینگ"] },
];

export const RESTAURANT_CONSUMABLES: Consumable[] = [
  { id: "frying-oil", fa: "روغن سرخ‌کردنی و مایع (تن/لیتر)", consumption: 5, margin: [5, 10], regulated: false, keywords: ["oil", "yağ", "yag", "روغن", "frying"] },
  { id: "rice", fa: "برنج (ایرانی/بالدو/اوسمانجیک)", consumption: 5, margin: [6, 12], regulated: false, keywords: ["rice", "pirinç", "pirinc", "برنج"] },
  { id: "chicken", fa: "مرغ تازه/منجمد", consumption: 5, margin: [7, 13], regulated: false, certNote: "گواهی حلال و زنجیره سرد توصیه می‌شود", keywords: ["chicken", "tavuk", "مرغ", "جوجه"] },
  { id: "beef", fa: "گوشت قرمز (گوساله/گوسفندی)", consumption: 4, margin: [8, 15], regulated: false, certNote: "گواهی حلال و زنجیره سرد توصیه می‌شود", keywords: ["beef", "meat", "kırmızı et", "kirmizi et", "dana", "et ", "گوشت", "قصابی"] },
  { id: "vegetables", fa: "سبزیجات و صیفی‌جات تازه", consumption: 5, margin: [8, 18], regulated: false, certNote: "فسادپذیر — لجستیک سریع/سرد", keywords: ["vegetable", "sebze", "سبزیجات", "صیفی", "میوه", "salata"] },
  { id: "flour-bakery", fa: "آرد و مواد نانوایی", consumption: 4, margin: [6, 12], regulated: false, keywords: ["flour", "un ", "آرد", "نان", "ekmek"] },
  { id: "dairy", fa: "لبنیات (پنیر، ماست، کره)", consumption: 4, margin: [8, 15], regulated: false, certNote: "زنجیره سرد الزامی", keywords: ["dairy", "cheese", "peynir", "yoğurt", "yogurt", "لبنیات", "پنیر", "ماست", "کره"] },
  { id: "packaging", fa: "ظروف بیرون‌بر و بسته‌بندی", consumption: 4, margin: [10, 20], regulated: false, keywords: ["packag", "paket", "ظرف", "بسته‌بندی", "بیرون‌بر", "kutu"] },
  { id: "legumes-spices", fa: "حبوبات و ادویه‌جات", consumption: 3, margin: [12, 25], regulated: false, keywords: ["bakliyat", "baharat", "legume", "spice", "حبوبات", "ادویه", "پولکی"] },
  { id: "beverages", fa: "نوشیدنی و آب معدنی", consumption: 4, margin: [5, 10], regulated: false, keywords: ["beverage", "içecek", "icecek", "su ", "نوشیدنی", "آب معدنی", "نوشابه"] },
];

export const MARKETS = {
  clinics: {
    fa: "کلینیک‌ها و مراکز پزشکی ترکیه",
    regions: CLINIC_REGIONS,
    consumables: CLINIC_CONSUMABLES,
    regulatory: "Regulated goods (implants, fillers, toxin, threads) require TİTCK/ÜTS registration and licensed local distribution before supply.",
  },
  restaurants: {
    fa: "رستوران‌های استانبول",
    regions: RESTAURANT_REGIONS,
    consumables: RESTAURANT_CONSUMABLES,
    regulatory: "Food supply should follow halal certification and cold-chain rules for meat, poultry and dairy.",
  },
} as const;

export type MarketId = keyof typeof MARKETS;

export const REGION_ALIASES: Record<MarketId, Record<string, string>> = {
  clinics: {}, restaurants: {},
};
for (const mid of Object.keys(MARKETS) as MarketId[]) {
  for (const r of MARKETS[mid].regions) {
    REGION_ALIASES[mid][r.tr.toLowerCase()] = r.id;
    REGION_ALIASES[mid][r.fa] = r.id;
    REGION_ALIASES[mid][r.id] = r.id;
  }
}
Object.assign(REGION_ALIASES.restaurants, {
  "bağcılar": "bagcilar", "güngören": "gungoren", "küçükçekmece": "kucukcekmece",
  "ümraniye": "umraniye", "gaziosmanpaşa": "gaziosmanpasa", "istanbul": "istanbul", "استانبول": "istanbul",
});
Object.assign(REGION_ALIASES.clinics, {
  "şişli": "sisli", "sisli": "sisli", "kadıköy": "kadikoy", "bakırköy": "bakirkoy",
  "beşiktaş": "besiktas", "ataşehir": "atasehir", "beyoğlu": "beyoglu", "üsküdar": "uskudar",
  "bahçelievler": "bahcelievler", "beylikdüzü": "beylikduzu", "istanbul": "istanbul", "استانبول": "istanbul",
});

export function matchRegion(text: string, market: MarketId): string | null {
  const n = (text || "").trim().toLowerCase();
  if (!n) return null;
  for (const [alias, id] of Object.entries(REGION_ALIASES[market])) {
    if (alias && n.includes(alias)) return id;
  }
  return null;
}

export function matchCategory(text: string, market: MarketId): Consumable | null {
  const n = (text || "").toLowerCase();
  if (!n.trim()) return null;
  const scored: { item: Consumable; hits: number; long: number }[] = [];
  for (const item of MARKETS[market].consumables) {
    if (item.id === n) return item;
    let hits = 0, long = 0;
    for (const kw of item.keywords) {
      if (kw && n.includes(kw.toLowerCase())) { hits++; long = Math.max(long, kw.length); }
    }
    if (hits) scored.push({ item, hits, long });
  }
  scored.sort((a, b) => b.hits - a.hits || b.long - a.long);
  return scored[0]?.item ?? null;
}

function sha12(s: string): number {
  return parseInt(createHash("sha256").update(s, "utf8").digest("hex").slice(0, 12), 16);
}
export function sampleDet(seed: string, low: number, high: number): number {
  const span = Math.max(1, high - low + 1);
  return low + (sha12(seed) % span);
}
export function samplePhone(seed: string): string {
  return `+90 53${sampleDet(seed + "-t1", 0, 9)} ${sampleDet(seed + "-t2", 100, 999)} ${sampleDet(seed + "-t3", 1000, 9999)}`;
}

const SAMPLE_NEED_TEMPLATES: { categoryId: string; need: string; qty: [number, number]; budget: [number, number] }[] = [
  { categoryId: "frying-oil", need: "خرید هفتگی روغن سرخ‌کردنی (yağ) برای سرخ‌کردنی و دونر", qty: [200, 1200], budget: [25_000, 120_000] },
  { categoryId: "rice", need: "برنج ایرانی/ترک برای پلو روزانه", qty: [300, 1500], budget: [30_000, 150_000] },
  { categoryId: "chicken", need: "مرغ تازه روزانه (tavuk) برای کباب و سینی", qty: [300, 1500], budget: [60_000, 350_000] },
  { categoryId: "beef", need: "گوشت قرمز (kırmızı et) برای دونر و کوفته هفتگی", qty: [150, 900], budget: [80_000, 500_000] },
  { categoryId: "vegetables", need: "سبزیجات و صیفی تازه روزانه (sebze)", qty: [100, 800], budget: [15_000, 120_000] },
  { categoryId: "flour-bakery", need: "آرد نانوایی و پیتزا (un) ماهانه", qty: [500, 3000], budget: [20_000, 150_000] },
  { categoryId: "dairy", need: "پنیر و ماست (peynir/yoğurt) ماهانه", qty: [100, 500], budget: [20_000, 120_000] },
  { categoryId: "packaging", need: "ظرف بیرون‌بر و بسته‌بندی (paket) — عدد", qty: [5000, 85000], budget: [10_000, 120_000] },
  { categoryId: "legumes-spices", need: "حبوبات و ادویه (bakliyat/baharat) فصلی", qty: [50, 400], budget: [10_000, 80_000] },
  { categoryId: "beverages", need: "نوشیدنی و آب معدنی (içecek/su) ماهانه", qty: [300, 2000], budget: [8_000, 60_000] },
];
const RESTAURANT_NAMES = ["Anadolu", "Boğaz", "Hünkar", "Lezzet", "Saray", "Marmara", "Ege", "Kervan", "İstanbul", "Dostlar"];
const RESTAURANT_SUFFIXES = ["Sofrası", "Lokantası", "Kebap Evi", "Restoranı", "Ocakbaşı", "Pide Evi"];
const BASE_EPOCH = Date.UTC(2026, 7, 8);

export function makeSampleBids(count = 10): Bid[] {
  const bids: Bid[] = [];
  const n = Math.max(1, Math.min(count, 500));
  for (let i = 0; i < n; i++) {
    const region = RESTAURANT_REGIONS[i % RESTAURANT_REGIONS.length];
    const tpl = SAMPLE_NEED_TEMPLATES[i % SAMPLE_NEED_TEMPLATES.length];
    const head = RESTAURANT_NAMES[(i * 7 + 3) % RESTAURANT_NAMES.length];
    const tail = RESTAURANT_SUFFIXES[(i * 5 + 1) % RESTAURANT_SUFFIXES.length];
    const seed = `${region.id}-${i}`;
    const clinic = `رستوران ${head} ${tail}`;
    const deadline = new Date(BASE_EPOCH + ((i * 3) % 40) * 86_400_000).toISOString().slice(0, 10);
    bids.push({
      id: createHash("sha256").update(`restaurants|${clinic}|${tpl.need}|${deadline}`, "utf8").digest("hex").slice(0, 14),
      market: "restaurants", clinic, need: tpl.need, regionId: region.id, regionTr: region.tr,
      categoryId: tpl.categoryId,
      categoryFa: RESTAURANT_CONSUMABLES.find((c) => c.id === tpl.categoryId)?.fa ?? "متفرقه",
      quantity: sampleDet(seed + "-q", tpl.qty[0], tpl.qty[1]),
      budgetTry: sampleDet(seed + "-b", tpl.budget[0], tpl.budget[1]),
      deadline, contact: samplePhone(seed + "-p"), source: "seed-sample", sample: true,
    });
  }
  return bids;
}

const SAMPLE_SUPPLIER_DEFS: { name: string; region: string; zones: string[]; products: Omit<SupplierProduct, "categoryFa">[] }[] = [
  { name: "عمده‌فروشی Anadolu Gıda", region: "bagcilar", zones: [], products: [
    { categoryId: "chicken", name: "مرغ کامل منجمد", unit: "کیلوگرم", priceTry: 128, stock: 4000, minOrder: 100, deliveryDays: 1 },
    { categoryId: "frying-oil", name: "روغن آفتابگردان ۱۸ لیتری", unit: "لیتر", priceTry: 58, stock: 8000, minOrder: 200, deliveryDays: 1 },
    { categoryId: "rice", name: "برنج بالدو ترک", unit: "کیلوگرم", priceTry: 46, stock: 6000, minOrder: 250, deliveryDays: 2 } ] },
  { name: "تدارکات Marmara Et", region: "esenler", zones: ["bagcilar", "esenler", "kucukcekmece", "esenyurt"], products: [
    { categoryId: "beef", name: "گوشت گوساله بی‌استخوان", unit: "کیلوگرم", priceTry: 289, stock: 2500, minOrder: 50, deliveryDays: 1 },
    { categoryId: "chicken", name: "مرغ تازه تک‌تکه", unit: "کیلوگرم", priceTry: 134, stock: 3000, minOrder: 150, deliveryDays: 1 } ] },
  { name: "سبزیدار Boğaz Sebze", region: "gungoren", zones: [], products: [
    { categoryId: "vegetables", name: "سبد سبزیجات و صیفی رستورانی", unit: "کیلوگرم", priceTry: 32, stock: 5000, minOrder: 100, deliveryDays: 0 },
    { categoryId: "dairy", name: "پنیر سفید رستورانی", unit: "کیلوگرم", priceTry: 118, stock: 1200, minOrder: 40, deliveryDays: 1 } ] },
  { name: "توزیع Ege Unlu", region: "kucukcekmece", zones: [], products: [
    { categoryId: "flour-bakery", name: "آرد نانوایی نوع ۱", unit: "کیلوگرم", priceTry: 24, stock: 10000, minOrder: 300, deliveryDays: 2 },
    { categoryId: "packaging", name: "ظرف بیرون‌بر کرافت", unit: "عدد", priceTry: 2.1, stock: 200000, minOrder: 5000, deliveryDays: 2 } ] },
  { name: "لبنیات Karadeniz Süt", region: "esenyurt", zones: [], products: [
    { categoryId: "dairy", name: "ماست صبحانه ده‌کیلویی", unit: "کیلوگرم", priceTry: 112, stock: 2000, minOrder: 50, deliveryDays: 1 },
    { categoryId: "beverages", name: "آب معدنی ۱.۵ لیتری", unit: "عدد", priceTry: 9, stock: 20000, minOrder: 500, deliveryDays: 1 } ] },
  { name: "عمده Hünkar Baharat", region: "umraniye", zones: ["umraniye", "pendik", "kartal", "sultanbeyli"], products: [
    { categoryId: "legumes-spices", name: "عدس و لوبیا فله", unit: "کیلوگرم", priceTry: 68, stock: 1500, minOrder: 25, deliveryDays: 2 },
    { categoryId: "rice", name: "برنج اوسمانجیک", unit: "کیلوگرم", priceTry: 49, stock: 4000, minOrder: 200, deliveryDays: 2 } ] },
  { name: "تازه‌رسان Pera Tavukçuluk", region: "pendik", zones: [], products: [
    { categoryId: "chicken", name: "مرغ تازه روزانه", unit: "کیلوگرم", priceTry: 142, stock: 2000, minOrder: 80, deliveryDays: 0 } ] },
  { name: "روغن‌پخش Tarihi Yağ", region: "kartal", zones: [], products: [
    { categoryId: "frying-oil", name: "روغن سرخ‌کردنی حرفه‌ای", unit: "لیتر", priceTry: 61, stock: 6000, minOrder: 150, deliveryDays: 2 },
    { categoryId: "beverages", name: "نوشابه قوطی ۲۴ تایی", unit: "عدد", priceTry: 11, stock: 15000, minOrder: 480, deliveryDays: 2 } ] },
  { name: "قصابی Şehzade Kasap", region: "sultanbeyli", zones: ["sultanbeyli", "umraniye", "kartal", "pendik"], products: [
    { categoryId: "beef", name: "گوشت گوسفندی تازه", unit: "کیلوگرم", priceTry: 315, stock: 1800, minOrder: 40, deliveryDays: 1 } ] },
  { name: "بسته‌بان İstanbul Paket", region: "gaziosmanpasa", zones: [], products: [
    { categoryId: "packaging", name: "جعبه پیتزا و پک سلفونی", unit: "عدد", priceTry: 1.9, stock: 150000, minOrder: 3000, deliveryDays: 3 } ] },
];

export function makeSampleSuppliers(): Supplier[] {
  return SAMPLE_SUPPLIER_DEFS.map((d, i) => {
    const region = RESTAURANT_REGIONS.find((r) => r.id === d.region)!;
    return {
      id: createHash("sha256").update(`supplier|restaurants|${d.name}|${region.id}`, "utf8").digest("hex").slice(0, 14),
      market: "restaurants", name: d.name, regionId: region.id, regionFa: region.fa, regionTr: region.tr,
      phone: samplePhone(`sample-supplier-${i}`),
      deliveryZones: d.zones, sample: true, source: "seed-sample",
      products: d.products.map((p) => ({
        ...p,
        categoryFa: RESTAURANT_CONSUMABLES.find((c) => c.id === p.categoryId)?.fa ?? p.categoryId,
      })),
    };
  });
}

// ---- ratings (in-memory, per serverless isolate — ephemeral by design) ----
const RATINGS = new Map<string, { price: number[]; quality: number[]; delivery: number[]; satisfaction: number[] }>();

export function rateSupplier(id: string, scores: Partial<Record<"price" | "quality" | "delivery" | "satisfaction", number>>) {
  const cell = RATINGS.get(id) ?? { price: [], quality: [], delivery: [], satisfaction: [] };
  let added = 0;
  for (const k of ["price", "quality", "delivery", "satisfaction"] as const) {
    const v = scores[k];
    if (v === undefined || v === null) continue;
    if (typeof v !== "number" || Number.isNaN(v) || v < 1 || v > 5) {
      throw new Error(`Rating '${k}' must be between 1 and 5 (got ${v}).`);
    }
    cell[k].push(v); added++;
  }
  if (!added) throw new Error("Provide at least one of: price, quality, delivery, satisfaction (each 1..5).");
  RATINGS.set(id, cell);
  const avg = (a: number[]) => (a.length ? Math.round((a.reduce((x, y) => x + y, 0) / a.length) * 100) / 100 : null);
  const aspects = { price: avg(cell.price), quality: avg(cell.quality), delivery: avg(cell.delivery), satisfaction: avg(cell.satisfaction) };
  const present = Object.values(aspects).filter((x): x is number => x !== null);
  return {
    count: present.length ? Math.max(cell.price.length, cell.quality.length, cell.delivery.length, cell.satisfaction.length) : 0,
    avg: present.length ? Math.round((present.reduce((x, y) => x + y, 0) / present.length) * 100) / 100 : null,
    aspects, ephemeral: true,
  };
}

export function ratingOf(id: string) {
  const cell = RATINGS.get(id);
  if (!cell) return { avg: null as number | null, count: 0 };
  const all = [...cell.price, ...cell.quality, ...cell.delivery, ...cell.satisfaction];
  const groups = [cell.price, cell.quality, cell.delivery, cell.satisfaction].filter((g) => g.length);
  const aspectAvg = groups.map((g) => g.reduce((x, y) => x + y, 0) / g.length);
  return {
    avg: groups.length ? Math.round((aspectAvg.reduce((x, y) => x + y, 0) / groups.length) * 100) / 100 : null,
    count: Math.max(...[cell.price, cell.quality, cell.delivery, cell.satisfaction].map((g) => g.length), 0),
  };
}

// ---- bids scoring ----
function budgetFactor(b?: number | null): number {
  if (!b) return 1;
  if (b >= 1_000_000) return 1.45;
  if (b >= 250_000) return 1.3;
  if (b >= 50_000) return 1.15;
  return 1;
}
function deadlineFactor(deadline: string): number {
  if (!deadline) return 1;
  const t = Date.parse(deadline);
  if (Number.isNaN(t)) return 1;
  return t - Date.now() <= 30 * 86_400_000 ? 1.15 : 1;
}
export function scoredBid(b: Bid) {
  const market = (b.market in MARKETS ? b.market : "restaurants") as MarketId;
  const cat = MARKETS[market].consumables.find((c) => c.id === b.categoryId);
  const marginMid = cat ? (cat.margin[0] + cat.margin[1]) / 2 : 5;
  const base = Math.min(100, (cat?.consumption ?? 2) * marginMid * 2);
  const score = Math.round(Math.min(100, base * budgetFactor(b.budgetTry) * deadlineFactor(b.deadline)) * 10) / 10;
  return {
    ...b,
    opportunityScore: score,
    grade: score >= 70 ? "A" : score >= 45 ? "B" : "C",
    consumptionLevel: cat?.consumption ?? 0,
    marginRange: cat ? cat.margin : [0, 0],
    regionFa: MARKETS[market].regions.find((r) => r.id === b.regionId)?.fa ?? "استانبول (سایر)",
  };
}

export function opportunities(marketParam: string) {
  const markets: MarketId[] = marketParam === "all"
    ? (Object.keys(MARKETS) as MarketId[])
    : marketParam in MARKETS ? [marketParam as MarketId] : (() => { throw new Error(`Unknown market '${marketParam}'. Use one of: clinics, restaurants or 'all'`); })();
  const bids = makeSampleBids(10).map(scoredBid);
  const consumables = markets.flatMap((m) => MARKETS[m].consumables.map((c) => {
    const marginMid = (c.margin[0] + c.margin[1]) / 2;
    return { ...c, score: Math.round(c.consumption * marginMid * 10) / 10, activeBids: bids.filter((b) => b.categoryId === c.id).length };
  }));
  const topPicks = [...consumables].sort((a, b) => {
    const pa = Math.min(100, a.score * (1 + 0.05 * a.activeBids));
    const pb = Math.min(100, b.score * (1 + 0.05 * b.activeBids));
    return pb - pa;
  }).slice(0, 10).map((c) => ({ ...c, recommendationScore: Math.round(Math.min(100, c.score * (1 + 0.05 * c.activeBids)) * 10) / 10 }));
  consumables.sort((a, b) => b.score - a.score);
  const regions = markets.flatMap((m) => MARKETS[m].regions.map((r) => ({
    ...r, opportunity: r.demand * 20 + bids.filter((b) => b.regionId === r.id).length * 5,
  })));
  const scopedBids = bids.filter((b) => (markets as string[]).includes(b.market));
  return {
    ok: true,
    title: "Turkey — " + markets.map((m) => MARKETS[m].fa).join(" + ") + " (Istanbul focus)",
    summary: {
      regionCount: regions.length, consumableCategories: consumables.length,
      activeBids: scopedBids.length, sampleBids: scopedBids.filter((b) => b.sample).length,
      webhookConfigured: false,
    },
    consumables, topPicks, regions, bids: scopedBids,
    samplesNote: scopedBids.some((b) => b.sample)
      ? `${scopedBids.filter((b) => b.sample).length} of these bids are educational samples with fictional +90 contacts — not real RFQs.` : null,
    disclaimer: "Rankings are advisory estimates based on consumption × indicative margin, not quotes or guarantees. "
      + markets.map((m) => MARKETS[m].regulatory).join(" "),
  };
}

// ---- supplier compare ----
export interface Offer {
  supplierId: string; supplier: string; regionId: string; regionFa: string; phone: string;
  product: string; unit: string; priceTry: number; stock: number | null; minOrder: number;
  deliveryDays: number; ratingAvg: number | null; ratingCount: number; deliversHere: boolean; sample: boolean;
}

export function offersFor(categoryId: string, regionId: string | null): Offer[] {
  const offers: Offer[] = [];
  for (const s of makeSampleSuppliers()) {
    const deliversHere = !regionId || s.deliveryZones.length === 0 || s.deliveryZones.includes(regionId);
    const rating = ratingOf(s.id);
    for (const p of s.products) {
      if (p.categoryId !== categoryId) continue;
      offers.push({
        supplierId: s.id, supplier: s.name, regionId: s.regionId, regionFa: s.regionFa, phone: s.phone,
        product: p.name, unit: p.unit, priceTry: p.priceTry, stock: p.stock, minOrder: p.minOrder,
        deliveryDays: p.deliveryDays, ratingAvg: rating.avg, ratingCount: rating.count,
        deliversHere, sample: s.sample,
      });
    }
  }
  offers.sort((a, b) => a.priceTry - b.priceTry || a.deliveryDays - b.deliveryDays);
  return offers;
}

function bestOffer(pool: Offer[]): Offer | null {
  if (!pool.length) return null;
  const cheapest = Math.min(...pool.map((o) => o.priceTry));
  const rated = pool.filter((o) => (o.ratingAvg ?? 0) >= 4.5);
  const near = rated.filter((o) => o.priceTry <= cheapest * 1.08);
  if (near.length) return near.sort((a, b) => (b.ratingAvg ?? 0) - (a.ratingAvg ?? 0) || a.priceTry - b.priceTry)[0];
  return pool.find((o) => o.priceTry === cheapest) ?? pool[0];
}

export function compare(categoryText: string, market: string, region?: string | null) {
  if (!(market in MARKETS)) throw new Error(`Unknown market '${market}'. Use one of: clinics, restaurants`);
  const m = market as MarketId;
  const category = matchCategory(categoryText, m);
  if (!category) {
    const known = MARKETS[m].consumables.slice(0, 5).map((c) => c.fa.split(" (")[0]).join("، ");
    throw new Error(`No product category matched '${categoryText.slice(0, 40)}'. Try e.g.: ${known} …`);
  }
  let regionId: string | null = null;
  if (region) {
    regionId = matchRegion(region, m);
    if (!regionId) throw new Error(`Unknown region '${region.slice(0, 40)}' for market '${m}'.`);
  }
  const offers = offersFor(category.id, regionId);
  const stats = offers.length ? (() => {
    const prices = offers.map((o) => o.priceTry);
    const min = Math.min(...prices), max = Math.max(...prices);
    return {
      min, max, avg: Math.round((prices.reduce((a, b) => a + b, 0) / prices.length) * 100) / 100,
      spreadPct: min ? Math.round(((max - min) / min) * 1000) / 10 : 0,
      offerCount: offers.length, inZoneCount: offers.filter((o) => o.deliversHere).length,
    };
  })() : null;
  const inZone = offers.filter((o) => o.deliversHere);
  const best = bestOffer(inZone.length ? inZone : offers);
  return {
    ok: true, market: m,
    category: { id: category.id, fa: category.fa, certNote: category.certNote },
    regionId,
    offers: offers.slice(0, 50),
    stats,
    recommendation: best && stats ? {
      supplierId: best.supplierId, supplier: best.supplier, priceTry: best.priceTry, unit: best.unit,
      reason: best.priceTry === stats.min && best.deliversHere ? "قیمت مناسب در محدوده شما"
        : (best.ratingAvg ?? 0) >= 4.5 ? "امتیاز بالا (≥۴.۵) با قیمت نزدیک به ارزان‌ترین" : "ارزان‌ترین پیشنهاد موجود",
    } : null,
    samplesNote: offers.some((o) => o.sample)
      ? "Some offers are from educational sample suppliers with fictional contacts." : null,
    message: offers.length ? null : "هیچ تأمین‌کننده‌ای برای این دسته ثبت نشده است.",
    disclaimer: "Prices are snapshots reported by suppliers; confirm before ordering.",
  };
}

// ---- smart plan ----
const PER_DIGITS = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩";
function asciiDigits(s: string): string {
  return s.split("").map((ch) => {
    const i = PER_DIGITS.indexOf(ch);
    return i >= 0 ? String(i % 10) : ch;
  }).join("");
}

export function parseNeedsText(text: string, market: MarketId): { category: string; qty: number }[] {
  const merged = new Map<string, number>();
  for (const chunk of asciiDigits(text || "").split(/[,،;؛\n]/).slice(0, 30)) {
    const clean = chunk.trim();
    if (!clean) continue;
    const cat = matchCategory(clean, market);
    const nums = clean.match(/\d+(?:[.,]\d+)?/g);
    const qty = nums ? Math.round(parseFloat(nums[0].replace(",", ""))) : 0;
    if (cat && qty > 0) merged.set(cat.id, (merged.get(cat.id) ?? 0) + qty);
  }
  return [...merged.entries()].map(([category, qty]) => ({ category, qty })).slice(0, 20);
}

export function smartPlan(input: { market?: string; region?: string; needs?: { category?: string; qty?: number }[]; text?: string }) {
  const market = (input.market || "restaurants") as MarketId;
  if (!(market in MARKETS)) throw new Error(`Unknown market '${input.market}'. Use one of: clinics, restaurants`);
  let regionId: string | null = null;
  if (input.region) {
    regionId = matchRegion(input.region, market);
    if (!regionId) throw new Error(`Unknown region '${input.region.slice(0, 40)}' for market '${market}'.`);
  }
  const merged = new Map<string, number>();
  const dropped: string[] = [];
  for (const raw of (input.needs ?? []).slice(0, 20)) {
    const label = String(raw?.category ?? "").slice(0, 40);
    const cat = matchCategory(label, market);
    const qty = Math.round(Number(raw?.qty) || 0);
    if (cat && qty > 0) merged.set(cat.id, (merged.get(cat.id) ?? 0) + qty);
    else if (label) dropped.push(label);
  }
  if (!merged.size && input.text) {
    for (const n of parseNeedsText(input.text, market)) merged.set(n.category, (merged.get(n.category) ?? 0) + n.qty);
  }
  if (!merged.size) throw new Error("Provide needs like {\"needs\": [{\"category\": \"مرغ\", \"qty\": 200}]} or text: «مرغ 200، روغن 40».");

  const warnings: string[] = [];
  if (dropped.length) warnings.push("این اقلام شناسایی نشدند و از سبد کنار گذاشته شدند: " + dropped.join("، "));
  const lines = [];
  let grandTotal = 0, marketTotal = 0, samplesUsed = false;
  for (const [categoryId, qty] of merged) {
    const categoryFa = MARKETS[market].consumables.find((c) => c.id === categoryId)?.fa ?? categoryId;
    const all = offersFor(categoryId, regionId);
    const pool = all.filter((o) => o.deliversHere).length ? all.filter((o) => o.deliversHere) : all;
    if (!pool.length) { warnings.push(`برای «${categoryFa}» هیچ پیشنهادی ثبت نشده است.`); continue; }
    const avgPrice = Math.round((pool.reduce((a, o) => a + o.priceTry, 0) / pool.length) * 100) / 100;
    marketTotal += avgPrice * qty;
    const best = bestOffer(pool)!;
    const ordered = [best, ...pool.filter((o) => o !== best)];
    let remaining = qty;
    const picks = [];
    for (const offer of ordered) {
      if (remaining <= 0) break;
      if (offer.stock !== null && offer.stock <= 0) continue;
      const cap = offer.stock !== null ? offer.stock : remaining;
      let take = Math.min(remaining, cap);
      let note: string | null = null;
      if (take < offer.minOrder) {
        take = Math.min(Math.max(offer.minOrder, remaining === qty ? qty : take), cap);
        note = `به حداقل سفارش ${offer.minOrder} ${offer.unit} افزایش یافت`;
      }
      if (take <= 0) continue;
      const lineTotal = Math.round(take * offer.priceTry * 100) / 100;
      grandTotal += lineTotal;
      samplesUsed = samplesUsed || offer.sample;
      picks.push({
        supplierId: offer.supplierId, supplier: offer.supplier,
        qty: take, unit: offer.unit, priceTry: offer.priceTry, lineTotal,
        deliveryDays: offer.deliveryDays, phone: offer.phone, note,
      });
      remaining -= take;
    }
    if (remaining > 0.001) warnings.push(`موجودی اعلام‌شده برای «${categoryFa}» کافی نیست؛ ${Math.round(remaining)} واحد تأمین نشد.`);
    lines.push({
      categoryId, categoryFa, requestedQty: qty, avgMarketPrice: avgPrice,
      offersConsidered: pool.length, inZoneOffers: all.filter((o) => o.deliversHere).length, picks,
    });
  }
  grandTotal = Math.round(grandTotal * 100) / 100;
  marketTotal = Math.round(marketTotal * 100) / 100;
  return {
    ok: true, market, regionId, lines,
    totals: {
      grandTotal, avgMarketTotal: marketTotal,
      estimatedSavingsVsAvg: Math.round((marketTotal - grandTotal) * 100) / 100,
    },
    warnings,
    samplesNote: samplesUsed
      ? "Plan uses educational sample suppliers with fictional contacts; it shows the mechanics, not real quotes." : null,
    disclaimer: "This is a planning suggestion computed from supplier-reported prices, not a binding order.",
  };
}
