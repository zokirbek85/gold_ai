// Content for the beginner guide page (/guide). Plain Uzbek, no trading jargon
// without an explanation. Reason codes mirror backend/strategy/engine.py and live.py.

export interface Term {
  term: string;
  short: string;
  long: string;
  example?: string;
  group: "asos" | "signal" | "risk" | "tizim";
}

export const GLOSSARY: Term[] = [
  {
    term: "XAUUSD", group: "asos",
    short: "Oltinning AQSh dollaridagi narxi",
    long: "XAU — oltin, USD — AQSh dollari. 1 troya unsiya (≈31.1 gramm) oltin necha dollar turishini ko‘rsatadi.",
    example: "XAUUSD = 4100 → 1 unsiya oltin 4 100 dollar.",
  },
  {
    term: "BUY (sotib olish)", group: "signal",
    short: "Narx ko‘tariladi deb kutish",
    long: "Hozir arzonroq sotib olib, keyin qimmatroq yopish. Narx ko‘tarilsa — foyda, tushsa — zarar.",
    example: "4000 da BUY, narx 4050 ga chiqdi → har unsiyada +50 $.",
  },
  {
    term: "SELL (sotish)", group: "signal",
    short: "Narx tushadi deb kutish",
    long: "Brokerda oltinni avval «sotib», keyin arzonroq «qaytarib olish». Narx tushsa — foyda, ko‘tarilsa — zarar.",
    example: "4000 da SELL, narx 3960 ga tushdi → har unsiyada +40 $.",
  },
  {
    term: "NO TRADE", group: "signal",
    short: "Hozir savdo qilmang",
    long: "Shartlar yetarlicha yaxshi emas. Bu xato emas — tizim sizni sifatsiz savdodan himoya qilyapti. Vaqtning katta qismida aynan shu javob chiqadi.",
  },
  {
    term: "Entry (kirish narxi)", group: "signal",
    short: "Savdoni ochish narxi",
    long: "Signal hisoblangan paytdagi narx. Real kirish shu narxga yaqin bo‘lishi kerak.",
  },
  {
    term: "Kirish zonasi", group: "signal",
    short: "Kirish mumkin bo‘lgan narx oralig‘i",
    long: "Narx shu oraliqda bo‘lsa, savdoni ochish mumkin. Narx zonadan chiqib ketgan bo‘lsa — signal eskirgan, «quvlamang».",
    example: "Zona 3994–4002, hozirgi narx 4010 → kirmang.",
  },
  {
    term: "Stop Loss (SL)", group: "risk",
    short: "Zararni cheklash darajasi",
    long: "Narx shu darajaga yetsa, savdo avtomatik yopiladi va zarar shu yerda to‘xtaydi. SL qo‘yilmagan savdo — eng katta xavf.",
    example: "BUY 4000, SL 3980 → eng ko‘pi bilan har unsiyada 20 $ zarar.",
  },
  {
    term: "Take Profit (TP)", group: "risk",
    short: "Foydani olish darajasi",
    long: "Narx shu darajaga yetsa, savdo avtomatik foyda bilan yopiladi.",
  },
  {
    term: "TP1", group: "risk",
    short: "Oraliq foyda nuqtasi (1R)",
    long: "Asosiy TP gacha bo‘lgan yo‘lning taxminan 40% i. Ma'lumot uchun ko‘rsatiladi: xohlasangiz bu yerda pozitsiyaning bir qismini yopishingiz mumkin. Backtest asosiy TP bo‘yicha hisoblangan.",
  },
  {
    term: "R (risk birligi)", group: "risk",
    short: "Bitta savdoda tavakkal qilingan summa",
    long: "1R = kirish va SL orasidagi masofa (pul ko‘rinishida — yo‘qotishga tayyor bo‘lgan summa). +2.5R = tavakkal qilingan summaning 2.5 barobari foyda; −1R = to‘liq SL.",
    example: "Har savdoda 50 $ tavakkal qilasiz: +2.5R = +125 $, −1R = −50 $.",
  },
  {
    term: "Risk/Reward (R/R)", group: "risk",
    short: "Mumkin bo‘lgan foyda ÷ mumkin bo‘lgan zarar",
    long: "R/R = 2.5 bo‘lsa, har 1 $ tavakkal uchun 2.5 $ foyda kutiladi. Shuning uchun yutqazgan savdolar ko‘p bo‘lsa ham, umumiy natija musbat bo‘lishi mumkin.",
  },
  {
    term: "Lot", group: "risk",
    short: "Savdo hajmi",
    long: "Ko‘pchilik brokerlarda 1 lot = 100 unsiya oltin. 0.01 lot = 1 unsiya: narx 1 $ o‘zgarsa, foyda yoki zarar 1 $. Brokeringiz shartini albatta tekshiring.",
    example: "0.10 lot, narx 10 $ ga ko‘tarildi → 0.10 × 100 × 10 = 100 $.",
  },
  {
    term: "Risk %", group: "risk",
    short: "Bitta savdoda hisobning necha foizini tavakkal qilish",
    long: "Tizim standart holatda 0.5% ni oladi. 10 000 $ hisobda bu har savdoda eng ko‘pi bilan 50 $ zarar degani. Yangi boshlovchiga 1% dan oshirmaslik tavsiya etiladi.",
  },
  {
    term: "Spread", group: "asos",
    short: "Sotib olish va sotish narxi orasidagi farq",
    long: "Brokerning olinadigan haqi. Savdo ochilishi bilanoq spread miqdorida «minus»da turasiz. Yangiliklar paytida spread bir necha barobar kengayadi.",
  },
  {
    term: "Slippage", group: "asos",
    short: "Kutilgan va haqiqiy narx farqi",
    long: "Bozor tez harakatlanganda buyurtma biroz boshqa narxda bajariladi. Tizim har bir bajarilishda 0.10 $ slippage hisoblaydi.",
  },
  {
    term: "Signal score", group: "signal",
    short: "Qoidalar qanchalik yaxshi bajarilgani (0–100)",
    long: "Bu YUTISH EHTIMOLI EMAS. 80 ball «80% yutadi» degani emas. Score faqat setupning sifat belgilarini qo‘shib chiqadi. Sahifalarda «Confidence» deb ko‘rsatilgan raqam ham aynan shu score.",
  },
  {
    term: "Bozor rejimi", group: "tizim",
    short: "Bozorning hozirgi «xarakteri»",
    long: "TREND_UP — barqaror ko‘tarilish, TREND_DOWN — barqaror tushish, RANGE — yonlama harakat, TRANSITION — aniq emas, HIGH/LOW_VOLATILITY — juda keskin yoki juda sust. Tizim faqat trend rejimida signal beradi.",
  },
  {
    term: "H4 / D1", group: "tizim",
    short: "4 soatlik va kunlik shamlar",
    long: "Bitta sham = shu vaqt ichidagi narx harakati (ochilish, eng yuqori, eng past, yopilish). Tizim D1 (kunlik) bilan umumiy yo‘nalishni, H4 (4 soatlik) bilan kirish nuqtasini aniqlaydi.",
  },
  {
    term: "Pullback", group: "tizim",
    short: "Trend ichidagi vaqtinchalik orqaga qaytish",
    long: "Narx ko‘tarilish trendida biroz tushadi, keyin yana ko‘tarila boshlaydi. Tizim aynan shu «dam olish»dan keyin qayta harakatlanish paytini qidiradi.",
  },
  {
    term: "Paper trading", group: "tizim",
    short: "Virtual pul bilan savdo",
    long: "Tizim o‘z signallarini 10 000 $ lik virtual hisobda haqiqiy narxlar bo‘yicha o‘zi sinaydi. Real pul ishlatilmaydi. Natijasini tekshirishning eng xavfsiz usuli.",
  },
  {
    term: "Drawdown", group: "risk",
    short: "Eng yuqori nuqtadan keyingi pasayish",
    long: "Hisob 10 000 $ dan 9 500 $ ga tushsa — drawdown 5%. Paper hisobda 10% ga yetsa, yangi savdolar avtomatik to‘xtaydi.",
  },
  {
    term: "Backtest", group: "tizim",
    short: "Strategiyani o‘tmish ma'lumotlarida sinash",
    long: "«Agar shu qoidalar bilan o‘tmishda savdo qilganimda nima bo‘lardi?» degan savolga javob. Yaxshi backtest kelajakdagi foydani kafolatlamaydi.",
  },
];

export interface Reason {
  code: string;
  title: string;
  meaning: string;
  action: string;
  kind: "bozor" | "malumot" | "risk" | "himoya";
}

export const REASONS: Reason[] = [
  { code: "RANGE_DISABLED", kind: "bozor", title: "Bozor yonlama harakatlanyapti",
    meaning: "Narx aniq yo‘nalishsiz, ma'lum oraliqda u yoq-bu yoqqa yuryapti. Bu sharoit uchun sinovdan o‘tgan strategiya yo‘q.",
    action: "Kuting. Trend paydo bo‘lganda tizim o‘zi aytadi." },
  { code: "TRANSITION", kind: "bozor", title: "Trend ham, range ham emas",
    meaning: "Bozor bir holatdan boshqasiga o‘tyapti, yo‘nalish noaniq.",
    action: "Kuting." },
  { code: "HTF_CONFLICT", kind: "bozor", title: "Katta va kichik timeframe bir-biriga zid",
    meaning: "4 soatlik grafikda trend bor, lekin kunlik grafik buni tasdiqlamayapti. Zid yo‘nalishdagi savdolar ko‘proq zarar bergan.",
    action: "Kuting — ikkalasi bir yo‘nalishga kelishi kerak." },
  { code: "NO_PULLBACK", kind: "bozor", title: "Narx dam olmadi — kirish kech",
    meaning: "Trend bor, lekin narx orqaga qaytmasdan ko‘tarilib (yoki tushib) ketgan. Hozir kirish — eng yuqori nuqtada sotib olish xavfi.",
    action: "Narx orqaga qaytishini kuting." },
  { code: "PULLBACK_TOO_DEEP", kind: "bozor", title: "Orqaga qaytish juda chuqur",
    meaning: "Narx shunchalik ko‘p qaytdiki, trend buzilgan bo‘lishi mumkin.",
    action: "Kuting." },
  { code: "NO_TRIGGER", kind: "bozor", title: "Tasdiqlovchi sham yo‘q",
    meaning: "Setup shakllanmoqda, lekin narx hali trend yo‘nalishida qayta harakatlanganini ko‘rsatmadi.",
    action: "Keyingi 4 soatlik shamni kuting — signal paydo bo‘lishi mumkin." },
  { code: "RSI_OVERBOUGHT", kind: "bozor", title: "Narx juda tez ko‘tarilgan",
    meaning: "Ko‘tarilish haddan oshgan, sotib olish uchun kech.",
    action: "Kuting." },
  { code: "RSI_OVERSOLD", kind: "bozor", title: "Narx juda tez tushgan",
    meaning: "Tushish haddan oshgan, sotish uchun kech.",
    action: "Kuting." },
  { code: "VOLATILITY_TOO_HIGH", kind: "bozor", title: "Bozor juda keskin",
    meaning: "Narx odatdagidan ikki baravardan ko‘p tebranyapti. Bunday paytda SL tez urib ketadi.",
    action: "Bozor tinchlanishini kuting." },
  { code: "VOLATILITY_TOO_LOW", kind: "bozor", title: "Bozor juda sust",
    meaning: "Harakat kam — foyda xarajatlarni qoplamasligi mumkin.",
    action: "Kuting." },
  { code: "ROLLOVER_SESSION", kind: "bozor", title: "Kun almashish vaqti (21:00–23:00 UTC)",
    meaning: "Bu soatlarda brokerlar spreadni kengaytiradi va likvidlik past bo‘ladi.",
    action: "Keyinroq qayta tekshiring." },
  { code: "SL_TOO_WIDE", kind: "risk", title: "Stop Loss juda uzoq",
    meaning: "Mantiqiy SL joyi narxdan juda uzoqda — zarar haddan tashqari katta bo‘lardi.",
    action: "Bu savdoni o‘tkazib yuboring." },
  { code: "RR_TOO_LOW", kind: "risk", title: "Foyda/zarar nisbati past",
    meaning: "Xarajatlardan keyin kutilgan foyda tavakkalga arzimaydi.",
    action: "O‘tkazib yuboring." },
  { code: "SPREAD_TOO_HIGH", kind: "risk", title: "Spread juda katta",
    meaning: "Brokerning narx farqi ruxsat etilganidan yuqori (odatda yangiliklar paytida).",
    action: "Spread normal holatga qaytishini kuting." },
  { code: "SPREAD_TOO_HIGH_VS_SL", kind: "risk", title: "Spread SL ga nisbatan katta",
    meaning: "Spread SL masofasining 15% idan oshadi — savdo boshidanoq juda «minus»da bo‘ladi.",
    action: "O‘tkazib yuboring." },
  { code: "NO_ROOM_TO_TARGET", kind: "risk", title: "Maqsadgacha joy yo‘q",
    meaning: "Yo‘lda narxni to‘xtatishi mumkin bo‘lgan kuchli daraja juda yaqin.",
    action: "O‘tkazib yuboring." },
  { code: "NEWS_BLACKOUT", kind: "himoya", title: "Muhim yangilik yaqin",
    meaning: "±30 daqiqa ichida AQSh uchun muhim iqtisodiy e'lon (NFP, CPI, FOMC). E'lon paytida narx bir daqiqada 10 $ dan ko‘proq sakrashi mumkin.",
    action: "E'londan keyin kamida 30 daqiqa kuting." },
  { code: "STRATEGY_SUSPENDED", kind: "himoya", title: "Strategiya vaqtincha to‘xtatilgan",
    meaning: "So‘nggi natijalar kutilganidan statistik jihatdan ancha yomon. Tizim kapitalni himoya qilish uchun o‘zini to‘xtatdi.",
    action: "Signal bermaydi. Qayta yoqish — faqat administrator qarori bilan." },
  { code: "SIGNAL_EXPIRED", kind: "himoya", title: "Signal eskirgan",
    meaning: "Amal qilish muddati (taxminan 8 soat) o‘tib ketgan.",
    action: "Kirmang. Yangi signalni kuting." },
  { code: "PRICE_LEFT_ENTRY_ZONE", kind: "himoya", title: "Narx kirish zonasidan chiqib ketgan",
    meaning: "Signal to‘g‘ri edi, lekin narx allaqachon uzoqlashgan. Endi kirish — yomonroq narxda kirish.",
    action: "Quvlamang. Keyingi signalni kuting." },
  { code: "SL_ALREADY_HIT", kind: "himoya", title: "Narx SL ga yetib bo‘lgan",
    meaning: "Siz kirishingizdan oldin narx stop darajasiga yetgan — setup buzilgan.",
    action: "Kirmang." },
  { code: "DATA_", kind: "malumot", title: "Narx ma'lumotlari muammosi",
    meaning: "Ma'lumot eskirgan (STALE), yetarli emas (INSUFFICIENT), bozor yopiq (MARKET_CLOSED — dam olish kunlari) yoki ishonchsiz (UNRELIABLE).",
    action: "Dam olish kunida — dushanbani kuting. Ish kunida bo‘lsa — administratorga xabar bering." },
  { code: "CONTEXT_", kind: "malumot", title: "Kunlik (D1) ma'lumot muammosi",
    meaning: "Umumiy yo‘nalishni aniqlash uchun kunlik tarix yetarli emas yoki yo‘q.",
    action: "Administratorga xabar bering." },
  { code: "INSUFFICIENT_HISTORY", kind: "malumot", title: "Tarix yetarli emas",
    meaning: "Indikatorlarni hisoblash uchun shamlar soni kam.",
    action: "Kuting yoki administratorga xabar bering." },
];

export function findReason(code: string): Reason | undefined {
  return REASONS.find(r => r.code === code) ??
    REASONS.find(r => r.code.endsWith("_") && code.startsWith(r.code));
}

export interface QuizQ {
  q: string;
  options: string[];
  answer: number;
  why: string;
}

export const QUIZ: QuizQ[] = [
  {
    q: "Tizim «NO TRADE» dedi. Nima qilasiz?",
    options: ["Baribir o‘zim savdo ochaman", "Kutaman — bu himoya", "Dasturni qayta ishga tushiraman"],
    answer: 1,
    why: "NO TRADE xato emas. Shartlar yomon bo‘lganda savdo qilmaslik — strategiyaning eng muhim qismi.",
  },
  {
    q: "Signal score = 80. Bu nimani anglatadi?",
    options: ["80% ehtimol bilan yutaman", "Setup qoidalari yaxshi bajarilgan, lekin kafolat yo‘q", "80 $ foyda olaman"],
    answer: 1,
    why: "Score — ehtimollik emas. Tarixda yutgan savdolar ham, yutqazganlar ham bo‘lgan.",
  },
  {
    q: "BUY signal: zona 3994–4002, hozirgi narx 4015. Nima qilasiz?",
    options: ["Darhol kiraman", "Kirmayman — narx zonadan chiqib ketgan", "SL ni olib tashlab kiraman"],
    answer: 1,
    why: "Zonadan tashqarida kirish — yomonroq narx va yomonroq R/R. «Quvlamang».",
  },
  {
    q: "Stop Loss qo‘yish kerakmi?",
    options: ["Har doim, signaldagi narxda", "Faqat zarar ko‘payganda", "Yo‘q, narx baribir qaytadi"],
    answer: 0,
    why: "SL siz uxlayotganingizda ham hisobingizni himoya qiladi. Barcha natijalar SL bilan hisoblangan.",
  },
  {
    q: "Ketma-ket 4 ta savdo zarar bilan yopildi. Bu nimani bildiradi?",
    options: ["Strategiya buzildi, hammasini to‘xtatish kerak", "Riskni oshirib, zararni qoplash kerak", "Bunday seriya tarixda ham bo‘lgan — rejaga amal qilish kerak"],
    answer: 2,
    why: "Testlarda ketma-ket 6 tagacha zarar bo‘lgan. Riskni oshirish eng xavfli xato. Haqiqiy muammo bo‘lsa, health monitor strategiyani o‘zi to‘xtatadi.",
  },
  {
    q: "Yaqin 10 daqiqada CPI (inflyatsiya) e'lon qilinadi. To‘g‘ri yo‘l?",
    options: ["Hozir savdo ochish — tez foyda", "E'londan keyin kamida 30 daqiqa kutish", "Lotni ikki barobar qilish"],
    answer: 1,
    why: "E'lon paytida volatillik ~5 barobar oshadi va spread kengayadi. Tarixiy testda yangilik atrofidagi oddiy qoidalar xarajatlardan keyin zarar bergan.",
  },
];

export const CHECKLIST = [
  { id: "signal", text: "Signal BUY yoki SELL (NO TRADE emas)", why: "NO TRADE bo‘lsa — savdo yo‘q." },
  { id: "fresh", text: "Amal qilish muddati (expires) hali o‘tmagan", why: "Eskirgan signal — bekor signal." },
  { id: "zone", text: "Hozirgi narx kirish zonasi ichida", why: "Zonadan tashqarida kirmang." },
  { id: "news", text: "Yaqin 30 daqiqada muhim yangilik yo‘q (Econ Calendar)", why: "NFP, CPI, FOMC paytida narx sakraydi." },
  { id: "risk", text: "Lot risk kalkulyatorida hisoblangan, risk ≤ 1%", why: "Bitta savdo hisobni yo‘qotmasligi kerak." },
  { id: "sl", text: "Stop Loss signaldagi narxda qo‘yildi", why: "SL siz yo‘qligingizda ham himoya qiladi." },
  { id: "tp", text: "Take Profit signaldagi narxda qo‘yildi", why: "Foydani reja bo‘yicha olish." },
  { id: "accept", text: "Bu savdo zarar bilan yopilishi mumkinligini qabul qilaman", why: "Har qanday strategiyada zararli savdolar bo‘ladi." },
];

export const PAGES = [
  { href: "/signals", name: "Signals", use: "Asosiy sahifa: «Generate» bilan yangi signal olish va eski signallarni ko‘rish.", trust: "ha" },
  { href: "/paper", name: "Paper Trading", use: "Tizimning virtual hisobdagi savdolari: balans, ochiq pozitsiya, natijalar, strategiya holati.", trust: "ha" },
  { href: "/dashboard", name: "Dashboard", use: "Umumiy ko‘rinish: narx, so‘nggi holat.", trust: "ha" },
  { href: "/charts", name: "Live Chart", use: "Narx grafigi — signaldagi darajalarni grafikda ko‘rish uchun.", trust: "ha" },
  { href: "/economic-calendar", name: "Econ Calendar", use: "Muhim yangiliklar vaqti. Savdodan oldin albatta tekshiring.", trust: "ha" },
  { href: "/backtesting", name: "Backtesting", use: "Strategiyaning o‘tmishdagi natijasi (xarajatlar bilan). Kam savdo bo‘lsa — ehtiyot.", trust: "ha" },
  { href: "/journal", name: "Trade Journal", use: "O‘zingizning real savdolaringizni yozib borish.", trust: "ha" },
  { href: "/news", name: "News", use: "Yangiliklar oqimi — ma'lumot uchun. Qarorlarga ta'sir qilmaydi.", trust: "malumot" },
  { href: "/market", name: "Live Market", use: "Joriy narx va bozor holati.", trust: "malumot" },
  { href: "/analysis", name: "Market Analysis", use: "Eski tahlil moduli — faqat ma'lumot uchun.", trust: "malumot" },
  { href: "/forecast", name: "Forecast", use: "Eski prognoz moduli — faqat ma'lumot uchun, signal emas.", trust: "malumot" },
  { href: "/ml", name: "Machine Learning", use: "Tekshiruvda ML modeli tasodifdan yaxshi bashorat qilmadi. Unga tayanmang.", trust: "yoq" },
];

export const FAQ = [
  { q: "Nega deyarli doim NO TRADE chiqadi?",
    a: "Strategiya faqat aniq trend + pullback + tasdiq bir vaqtda bo‘lganda signal beradi. Tarixda bu o‘rtacha oyiga 1–1.5 marta bo‘lgan. Kam, lekin sifatli signal — maqsad shu." },
  { q: "Dastur o‘zi savdo ochadimi?",
    a: "Yo‘q. Real hisobda savdoni faqat siz o‘zingiz brokerda qo‘lda ochasiz. Dastur faqat virtual (paper) hisobda o‘zini sinaydi. Real savdo funksiyasi kodda bloklangan." },
  { q: "Foyda kafolatlanadimi?",
    a: "Yo‘q. Tarixiy testda strategiya xarajatlardan keyin musbat natija ko‘rsatdi, lekin savdolar soni kam (42 ta) va natijaning bir qismi 2024–26 yillardagi oltin narxining o‘sishi bilan bog‘liq. O‘tmish kelajakni kafolatlamaydi." },
  { q: "Qaysi vaqtni ko‘rsatadi?",
    a: "Barcha vaqtlar UTC da. O‘zbekiston vaqti = UTC + 5 soat. Masalan, 08:00 UTC = 13:00 Toshkent." },
  { q: "Signal qachon yangilanadi?",
    a: "Tizim har soat :03 da bozorni o‘zi tekshiradi. Yangi 4 soatlik sham yopilgandan keyin yangi signal chiqishi mumkin. Generate tugmasi bir sham ichida bir xil natijani qaytaradi — bu dublikatdan himoya." },
  { q: "Qancha pul bilan boshlash kerak?",
    a: "Avval faqat demo hisobda boshlang. Real hisobga o‘tsangiz, yo‘qotishga tayyor bo‘lgan summa bilan va har savdoda 0.5–1% risk bilan. Juda kichik hisobda minimal lot (0.01) ham risk limitidan oshib ketishi mumkin — kalkulyator buni ko‘rsatadi." },
  { q: "Telegram'da qanday foydalanaman?",
    a: "Botga /signal yozing — joriy signal keladi. /price — narx, /status — tizim holati, /help — buyruqlar ro‘yxati." },
  { q: "Strategiya yomonlashsa nima bo‘ladi?",
    a: "Health monitor paper natijalarini backtest bilan solishtiradi. Natija ancha yomonlashsa, avval riskni 50% ga kamaytiradi, keyin signal berishni butunlay to‘xtatadi (STRATEGY_SUSPENDED)." },
];
