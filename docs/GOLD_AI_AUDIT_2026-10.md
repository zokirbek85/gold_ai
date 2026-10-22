# Gold_AI — Signal tizimi auditi, tuzatishlar va validatsiya (2026-10-22)

> Strategiya versiyasi: `v2.0.0`, konfiguratsiya xeshi `844353f1067e`.
> Barcha raqamlar `backend/strategy/research.py` bilan hisoblangan; xom natijalar:
> `docs/research/research_h4_d1.json`, `docs/research/research_h1_h4.json`.

## A. Executive summary

**Dastlabki holat.** Frontend `POST /api/v1/signals/generate` ni chaqiradi. U
`signal_service.generate_signal` (Technical 35% + SMC 25% + ML 20% + News 10% + Econ 10%
vaznli ball) va H4/H1/M15 EMA-konfluensiyadan foydalanadi. `/api/v1/ai/analyze`
(`gold_ai_engine`) alohida 8-bosqichli dvigatel. Real order ochilmaydi (bu saqlandi).

**Eng muhim muammolar (dalil bilan):**

1. **Bazadagi narx ma'lumotlari ifloslangan.** `candles` jadvalida real Twelvedata seriyasi
   bilan begona seriya aralashgan (bir sanada ≈$2 300 va ≈$4 000). D1'da 1 353 qatordan 510 tasi
   (38%), H4'da 200, H1'da 12, M5'da 81 — jami 803 qator. Begona qatorlar volume>0, 4 xonali narx,
   D1'da 08:00 timestamp bilan ajralib turadi. Qaysi kod yozgani git tarixidan aniqlanmadi.
2. **ADX formulasi xato** (`core/regime.py`): oxirgi silliqlash o'rtacha emas, yig'indi edi.
   ADX 0–100 o'rniga ~574 qaytargan, shuning uchun rejim deyarli doim "TRENDING" bo'lgan.
3. **`/ai/analyze` hech qachon signal bermagan.** TP'lar buffer'siz SL masofasidan hisoblangan,
   RR esa buffer bilan: RR1 = 1.5·d/(d+0.1·ATR), bu doim 1.5 dan kichik. 50 ta trend namunasida
   SL filtridan o'tgan 26 ta setupning hammasi "RR1 < 1.5" deb rad etilgan.
4. **Legacy SL juda tor.** SL eng yaqin swing'ga qo'yiladi va minimal masofa yo'q. Jonli misol:
   BUY entry 4164.66, **SL 4164.61 (5 sent)**, TP 4191.47 (RR ≈ 565). Backtestda xarajatlar
   688 savdoda 141.8R ni yegan.
5. **Hali yopilmagan sham va dam olish kunlarining "o'lik" shamlari ishlatilgan.** Twelvedata
   dam olish kunlari diapazoni ≈$0.25 bo'lgan shamlarni ham beradi (bazadagi H1'ning 28%i).
   Bu ATR, RSI va ADX'ni buzadi.
6. **Spread, slippage va komissiya hech qayerda hisobga olinmagan.** Eski `/backtesting/run`
   esa 5 shamda yopilmagan savdolarni tashlab yuborgan, savdolar ustma-ust tushgan,
   `max_drawdown` esa aslida ketma-ket zararlar soni bo'lgan.
7. **"Ishonch %" soxta edi:** `confidence = |ball − 50| × 3.33`, hech qanday kalibrovkasiz.
8. **Ishonchsiz kirishlar balga qo'shilgan.** Yangiliklar sentimenti oltin uchun yo'nalishsiz
   kalit so'zlardan olingan ("dollar rises" → bullish). ML eng *eski* 1 000 shamda va iflos
   ma'lumotda o'qitilgan, aniqligi tekshirilmagan.
9. **Iqtisodiy kalendar vaqt zonasi xato:** `-04:00` offset kesib tashlangan, ya'ni New York
   vaqti UTC deb saqlangan. Natijada yangilik blackout'i 4–5 soat siljigan.
10. **Frontend↔backend nomuvofiqligi.** Backtest sahifasi `metrics.*` kutadi, backend tekis
    kalitlar qaytargan. Legacy `NEUTRAL` qaytaradi, frontend tipida esa faqat
    `BUY | SELL | NO TRADE` bor.

**Bartaraf etildi:** 1 (o'qishda filtrlanadi va tozalash skripti tayyor, lekin bazaga
qo'llanmagan), 2, 3, 4 (v2 dvigatelda), 5, 6, 7, 8 (v2'da bu kirishlar qarorga ta'sir qilmaydi),
9, 10 (v2 yo'li uchun).

**Ochiq qoldi:** bazani tozalash sizning tasdig'ingizni kutmoqda. Bundan tashqari: yfinance
fallback spot emas, GC=F futures narxini beradi; legacy SMC/gold_ai_engine'dagi kichik mantiqiy
kamchiliklar; ikkita oldindan mavjud test xatosi; `.env`dagi `SECRET_KEY` default qiymatga
o'xshaydi; broker spetsifikatsiyasi (spread, kontrakt hajmi) tasdiqlanmagan.

**Asosiy xulosa.** Kod to'g'riligi va strategiyaning foydaliligi alohida masalalar.
- Kod xatolari tuzatildi va testlar bilan tasdiqlandi.
- Strategiya bo'yicha: v2 (H4 setup + D1 kontekst) train va test davrlarida xarajatlardan keyin
  musbat expectancy ko'rsatdi. Lekin savdolar soni kam (42 ta), standart xato katta, ta'sirning
  katta qismini D1 trend filtri va 2024–2026 bull bozori tushuntiradi.
- **Real savdoga tayyorlik isbotlanmagan.**

## B. Arxitektura va strategiya auditi

**Texnologiyalar.**
- Backend: FastAPI (Python 3.11), SQLAlchemy (sync), PostgreSQL 16, Redis, APScheduler.
- Frontend: Next.js 15 (o'zgartirilmadi).
- Ma'lumot manbalari: Twelvedata REST va WS, fallback sifatida yfinance (GC=F).
- ML: scikit-learn RandomForest.
- Interfeyslar: Telegram bot, ForexFactory JSON kalendari, RSS yangiliklar.
- Infratuzilma: Docker Compose (db, redis, backend, frontend, nginx).
- `src/` papkasi eski MT4 kodi bo'lib, faqat qisman import qilinadi (`src.signals.scorer`,
  `src.risk_management`).

**Signal zanjiri (v2, yangi default):**

```
POST /signals/generate
  → fetch_and_store(H4, D1)                       Twelvedata → candles jadvali (upsert)
  → _load_candles(H4 ×1500, D1 ×400)
  → strategy.live.generate
       clean_candles: invalid/dup/forming/weekend/begona seriya → DataQualityReport
       assess: tarix ≥250, eskirgan emas, bozor ochiq, gap ≤3
       news blackout: USD high-impact ±30 daq (kalendar UTC tuzatilgan)
       prepare_primary/context → attach_context (faqat YOPILGAN D1 sham)
       evaluate_bar → BUY / SELL / NO TRADE + reason_codes
       expiry / jonli narx entry-zonada / SL urilmagan
       position_size (pastga yaxlitlanadi, hech qachon oshirilmaydi)
       audit() → signal_audit.jsonl
  → dedup (bir yopilgan sham + qaror = bitta yozuv va bitta alert)
  → signals jadvali + Telegram (faqat BUY/SELL va dublikat bo'lmasa)
```

**Legacy strategiyaning kuchli tomonlari:** bir nechta ma'lumot manbasi; strukturaga asoslangan
SL g'oyasi; Telegram spam filtri.

**Legacy strategiyaning zaif tomonlari:**
- Indikatorlar bir-biriga zid: RSI kontrtrend, EMA200 esa trend bo'yicha ishlaydi.
- Rejim faqat nomigagina bor: ADX xato bo'lgani uchun vaznlar amalda o'zgarmagan.
- SL minimal masofasi yo'q va RR filtri yo'q.
- Xarajatlar hisobga olinmagan.
- News va ML tekshirilmagan holda vaznga qo'shilgan.

**v2 qoidalari** (testdan oldin belgilangan; `backend/strategy/engine.py`):

| Qism | Qoida |
|---|---|
| Kontekst (D1) | UP: EMA50 > EMA200, close > EMA50 va EMA50 o'sayotgan. DOWN shuning teskarisi. Boshqa holatda NONE |
| Rejim (H4) | ATR/median-ATR(100) > 2.0 → HIGH_VOLATILITY; < 0.5 → LOW_VOLATILITY; ADX ≥ 22 → TREND_UP/DOWN (EMA20 va EMA50 nisbatiga ko'ra); ADX < 18 → RANGE; oraliq qiymat → TRANSITION |
| BUY setup | TREND_UP va D1 UP. Oxirgi 5 shamda narx EMA20 ga qaytgan (low ≤ EMA20+0.25·ATR), lekin EMA50−0.25·ATR ostida yopilmagan. Trigger: bullish sham, oldingi high'dan yuqori va EMA20 ustida yopilish. RSI < 70 |
| SELL setup | BUY'ning ko'zgu nusxasi |
| SL | 5 shamlik swing ± 0.2·ATR. Masofa kamida 0.8·ATR. 2.5·ATR dan katta bo'lsa → NO TRADE |
| TP | 2.5R (TP1 = 1R, ma'lumot uchun) |
| Filtrlar | Spread ≤ 0.60. Spread/SL ≤ 15%. Xarajatlardan keyingi RR ≥ 1.5. 21–23 UTC rollover vaqtida signal yo'q |
| Amal qilish | 2 ta H4 sham (8 soat). Narx zonadan chiqsa yoki SL'ga yetsa bekor |
| Range rejimi | NO TRADE (range setupi train'da yordam bermadi) |
| Signal score | 0–100, nomlangan komponentlar yig'indisi. **Ehtimollik emas** |

## C. Bajarilgan tuzatishlar

| Fayl / modul | Eski muammo | Yangi yechim | Tasdiqlovchi test |
|---|---|---|---|
| `backend/strategy/` (yangi paket) | Qoidalar noaniq, xarajatlar yo'q, look-ahead xavfi | Toza, DB'siz modullar: `data_quality`, `indicators`, `engine`, `backtest`, `live`, `research`, `config` | `tests/test_strategy_v2.py` (47 test) |
| `routers/signals.py` `generate` | Legacy vaznli ball, forming sham, dublikatlar | `SIGNAL_ENGINE=v2` (default): v2 yo'li, ma'lumot tekshiruvi, har bir sham uchun dedup. `legacy` qiymati bilan eski yo'lga qaytish mumkin | `test_generate_endpoint_v2_and_dedup` |
| `routers/backtesting.py` | Xarajatsiz, yopilmagan savdolarni tashlaydi, `max_drawdown` = ketma-ket zararlar | v2 simulyatori: spread/slippage, konservativ intrabar, `metrics.*` frontend kontraktida | `TestBacktest` |
| `core/regime.py` `_adx` | ADX ~14× katta (574) | Wilder o'rtachasi, endi 0–100 (41.0) | `test_core_regime_adx_in_range`, `test_adx_method` |
| `core/regime.py` `detect` | VOLATILE deyarli hech qachon aniqlanmagan | Baza = so'nggi 14 TR'dan *oldingi* barlarning o'rtacha TR'i | `test_volatile_regime` (qayta yozildi) |
| `services/gold_ai_engine.py` `_build_signal` | RR1 doim < 1.5, signal yo'q | TP haqiqiy risk (buffer bilan) asosida | `test_gold_ai_engine_can_emit_signal_now` |
| `services/indicator_service.py` | `macd_hist` qaytarilmagan, MACD omili o'lik | `macd_hist` qo'shildi | `test_snapshot_has_macd_hist` |
| `services/calendar_service.py` | Offset kesilgan, vaqt 4–5 soat xato | UTC'ga to'g'ri konvertatsiya | `test_calendar_offset_converted_to_utc` |
| `services/market_service.py` | Noto'g'ri timestamp `utcnow()` ga aylangan, soxta sham paydo bo'lgan | Qator tashlab yuboriladi va log qilinadi | `test_twelvedata_bad_timestamp_rejected` |
| `services/scheduler.py` | ML eng eski 1 000 shamda o'qitilgan; H4 yangilanmagan | Eng yangi 1 000 sham ishlatiladi; H4 refresh qo'shildi | (kod tekshiruvi) |
| `services/telegram_service.py` | Sarlavhada "H1" qattiq yozilgan; soxta confidence filtri | TF dinamik; v2 signal'larda confidence chegarasi yo'q (dedup bor) | (kod tekshiruvi, Telegram jo'natilmadi) |
| `scripts/clean_contaminated_candles.py` (yangi) | Bazadagi begona seriya | Standart holatda dry-run; `--apply` faqat `DELETE` tasdig'i bilan ishlaydi | Offline tekshiruv: 803/803 sintetik qator, 0 ta false positive |
| `config.py`, `.env.example`, `docker-compose.yml` | — | `SIGNAL_ENGINE`, `GOLDAI_*` parametrlari | `docker compose config` ✓ |

## D. Test natijalari

| Test | Holat | Natija / izoh |
|---|---|---|
| Boshlang'ich to'plam (o'zgarishlardan oldin) | Bajarildi | 136 o'tdi, 4 yiqildi (2 ta ADX/VOLATILE + 2 ta quyida) |
| To'liq to'plam (o'zgarishlardan keyin) | Bajarildi | **185 o'tdi, 2 yiqildi** |
| `tests/test_strategy_v2.py` | Bajarildi | 47/47 o'tdi: indikatorlar, causality, ma'lumot sifati, BUY/SELL/NO TRADE, SL/TP, xarajatlar, backtest bajarilishi, risk, live, API, dedup, regression |
| `test_regime_detector.py` | Bajarildi | 11/11 o'tdi (oldin 2 ta yiqilgan edi) |
| `test_historical_analysis.py::test_seasonality_two_years` | Yiqildi (oldindan mavjud) | Alohida ishga tushirilganda o'tadi. Sabab: testlar umumiy in-memory DB'ni ulashadi. Signal zanjiriga aloqasi yo'q |
| `test_indicators.py::test_create_indicator_and_fetch_latest` | Yiqildi (oldindan mavjud) | Eski `src/` API'ga tegishli (reference-only kod) |
| Look-ahead tekshiruvi (real H4) | Bajarildi | 150 ta tasodifiy shamda kesilgan va to'liq ma'lumot qarorlari bir xil: 0 nomuvofiqlik |
| Backtest qayta tiklanishi | Bajarildi | Bir xil kirish → bir xil savdolar (`test_deterministic_and_no_lookahead`) |
| Real DB snapshot'ida live qaror | Bajarildi (faqat o'qish) | NO TRADE `RANGE_DISABLED`. H4'dan 172 ta, D1'dan 510 ta begona qator tashlandi |
| Frontend vizual tekshiruvi | **Bajarilmadi** | Frontend o'zgartirilmadi va ishga tushirilmadi |
| Telegram jo'natish | **Bajarilmadi** | Jonli xabar yuborilmadi |
| Docker image qayta build / deploy | **Bajarilmadi** | Ishlab turgan server hali eski koddа (image 4 oy oldin build qilingan) |

## E. Trading statistikasi

**Ma'lumotlar.**
- Twelvedata XAU/USD tarixi: H4 2020-11 … 2026-10 (9 999 sham), H1 2023-12 … 2026-10 (19 997 sham).
- Faqat o'qildi, bazaga yozilmadi.
- Tozalashdan keyin: H4 9 381 ta (617 ta dam olish shami tashlandi), H1 17 445 ta (2 552 ta tashlandi).

**Shartlar.**
- Spread $0.30, slippage $0.10 (har bir fill), komissiya 0. Bu **taxminiy qiymatlar** — broker
  ma'lumoti yo'q.
- Kirish keyingi sham open'ida. Bir sham ichida SL va TP ikkalasiga tegilsa → SL deb hisoblanadi.
- Bir vaqtda faqat bitta pozitsiya. 48 sham o'tgach vaqt bo'yicha chiqish.
- DD% — har savdoda 0.5% risk bilan hisoblangan.
- Legacy dvigatelga ML modeli berilmagan va news/econ = 50. Sababi: tarixiy news/kalendar
  ma'lumoti yo'q, mavjud model esa iflos ma'lumotda o'qitilgan.

**Test davri 2024-07-01 … 2026-10-22** (bir xil shartlar):

| Ko'rsatkich | Legacy H1 (hozirgi prod default)¹ | Legacy H4 | **v2 H4/D1** |
|---|---:|---:|---:|
| Signallar soni | 987 | 352 | 42 |
| Simulyatsiya qilingan savdolar | 984 | 351 | 42 |
| Win rate | 47.8% | 53.8% | 45.2% |
| Profit factor | 1.08 | 1.86 | 1.92 |
| Expectancy (R, xarajatdan keyin) | +0.047 (SE 0.095) | +0.412 (SE 0.364) | **+0.492 (SE 0.261)** |
| O'rtacha foyda / zarar (R) | +1.31 / −1.11 | +1.66 / −1.04 | +2.28 / −0.98 |
| Maksimal drawdown | 102.6R / 40.9% | 14.5R / 7.1% | **6.1R / 3.0%** |
| Ketma-ket zararlar (max) | 13 | 7 | 6 |
| Savdo xarajatlari (jami / bitta savdoga) | 77.3R / 0.079R | 13.9R / 0.040R | 0.67R / 0.016R |

¹ Legacy H1 test davri 2025-04-01 … 2026-10-22 (H1 tarixi qisqaroq).

**Train davri** (parametrlar faqat shu davrda tanlangan):

| | Legacy H1 (2024-01…2025-03) | Legacy H4 (2021-01…2024-06) | v2 H4/D1 (2021-01…2024-06) |
|---|---:|---:|---:|
| Savdolar | 688 | 566 | 44 |
| Expectancy | **−0.166R (SE 0.074)** | **−0.251R (SE 0.067)** | +0.360R (SE 0.259) |
| Max DD | 53.1% | 52.4% | 3.1% |

**Xulosalar va cheklovlar.**
- **Legacy beqaror.** Train'da statistik jihatdan aniq salbiy (≈ −2.2…−3.7 SE), test'da musbat,
  lekin shovqinli. Drawdown 0.5% risk'da 40–53% ga yetadi. Xarajatsiz hisoblanganda legacy H1
  test natijasi +0.111R, xarajatlar bilan +0.047R. Ya'ni eski backtest natijani shishirib
  ko'rsatgan.
- **v2 H4/D1 musbat, lekin statistik jihatdan ishonchli emas.**
  - Test: +0.49R, t ≈ 1.9. Train: +0.36R, t ≈ 1.4.
  - Grid'dagi 24 variantning hammasi test'da musbat chiqdi, demak natija parametr tanloviga
    sezgir emas.
  - Walk-forward (har 6 oyda train'da qayta tanlash, keyingi 6 oy OOS): 120 savdo, pooled
    **+0.273R**. Oynalar natijasi −0.07R dan +1.68R gacha.
- **Bozor drifti ta'siri katta.**
  - Test'dagi BUY savdolari: 36 ta, +0.63R.
  - SELL savdolari: atigi 6 ta, −0.31R. SELL tomoni validatsiya qilinmagan.
- **Tasodifiy nazorat** (bir xil bajarilish va xarajatlar, 200 ta seed):

  | Nazorat | Train o'rtacha | v2'dan yaxshilar | Test o'rtacha | v2'dan yaxshilar |
  |---|---:|---:|---:|---:|
  | Tasodifiy long | +0.05R | 1.5% | +0.23R | 7% |
  | D1 UP bo'lganda tasodifiy long | +0.18R | 24% | +0.39R | 32% |
  | Tasodifiy BUY/SELL | −0.03R | 1.5% | +0.04R | 1.5% |

  Bundan chiqadigan xulosa: edge'ning asosiy qismi D1 trend filtridan kelyapti. H4
  pullback/trigger vaqtlashining qo'shimcha qiymati statistik tasdiqlanmagan.
- **Xarajatlarga sezgirlik** (test): spread $0.20 → +0.494R, $0.30 → +0.492R, $0.50 → +0.488R.
  $0.80 da filtr barcha signallarni bloklaydi (`max_spread` = 0.60).
- **Signal score kalibrlanmagan.** Score ≥ 60: 40 savdo, +0.57R. Score < 60: 2 savdo.
  Taqqoslash uchun ma'lumot yetarli emas.
- **Xuddi shu qoidalar H1/H4 da ishlamaydi.** Tanlangan variant train'da +0.12R, test'da −0.22R
  bo'ldi; walk-forward 0.00R. Shuning uchun H1 default qilinmadi.
- **Signal chastotasi:** ~1.5 signal/oy (42 savdo / 28 oy). Bu sifat ustuvorligining narxi.
- **Metodologiya haqida halol eslatma.** v2 ning apriori H1 versiyasini to'liq davr bo'yicha bir
  marta ko'rganman. Shundan keyin H4/D1 gipotezasi qo'shildi; jami 2 gipoteza × 24 variant
  sinaldi. Ko'p sinov natijalarni optimistik qilishi mumkin.

## F. Ishga tushirish yo'riqnomasi

```bash
# 1. Testlar (Python 3.11)
uv venv --python 3.11 .venv311
VIRTUAL_ENV=.venv311 uv pip install -r backend/requirements.txt pytest PyJWT email-validator
DATABASE_URL=sqlite:///./test_gold_ai.db .venv311/bin/python -m pytest -q tests/

# 2. Backtestni qayta tiklash (CSV: timestamp,open,high,low,close,volume)
cd backend
ML_MODEL_DIR=/tmp/empty python -m strategy.research --h1 xau_4h.csv --primary-tf 240 \
    --context-tf 1440 --split 2024-07-01 --now 2026-10-22T07:00:00 --out results.json

# 3. Deploy (sizning qaroringiz; ishlab turgan servisni qayta ishga tushiradi)
docker compose build backend && docker compose up -d backend

# 4. Eski dvigatelga qaytish: .env'ga SIGNAL_ENGINE=legacy yozing va backend'ni qayta ishga tushiring

# 5. Signal audit logi (har bir qaror uchun bitta JSON qator)
docker compose exec backend tail -n 5 /app/ml_models/signal_audit.jsonl

# 6. Bazani tozalash — avval backup oling, so'ng dry-run qiling
docker compose exec db pg_dump -U goldai -t candles goldai > candles_backup.sql
DATABASE_URL=postgresql+psycopg2://goldai:<parol>@localhost:5432/goldai \
    python scripts/clean_contaminated_candles.py --export flagged.csv     # faqat hisobot
# ... flagged.csv ni ko'rib chiqing, keyin:  --apply
```

**Diagnostika.**
- `reason_codes` nima uchun NO TRADE bo'lganini ko'rsatadi:
  - ma'lumot: `DATA_STALE`, `CONTEXT_INSUFFICIENT_DATA`, `NEWS_BLACKOUT`;
  - bozor holati: `HTF_CONFLICT`, `RANGE_DISABLED`, `VOLATILITY_TOO_HIGH`;
  - narx va risk: `RR_TOO_LOW`, `SPREAD_TOO_HIGH`, `PRICE_LEFT_ENTRY_ZONE`.
- `data_status` har bir timeframe uchun nechta qator tashlanganini, gap'larni va
  ma'lumot yoshini ko'rsatadi.

**Taklif etiladigan boshlang'ich konservativ risk profili** (majburan o'rnatilmagan):
- risk 0.5% / savdo;
- `max_spread` $0.60;
- xarajatdan keyingi RR ≥ 1.5;
- bir vaqtda bitta pozitsiya;
- ketma-ket 6 ta zarardan keyin to'xtab, qayta ko'rib chiqish (test'dagi maksimum ham 6 edi).

Kontrakt hajmi (100 oz), lot qadami va spread'ni brokeringiz XAUUSD spetsifikatsiyasidan
tekshiring.

## G. Qolgan xavflar va keyingi bosqich

**Ochiq muammolar:**
- Bazadagi begona seriya (skript tayyor, qo'llanmagan).
- yfinance fallback GC=F futures narxini spot seriyaga aralashtirishi mumkin. Futures va spot
  o'rtasida basis farqi bor.
- Twelvedata WS bid/ask sintetik (`narx × 0.0002` ≈ $0.83) — real spread manbai yo'q.
- `gold_ai_engine` kamchiliklari: `_infer_direction` teng ballda BUY tomonga og'adi; doji
  ikkala yo'nalish uchun ham hisoblanadi; "+3 clean environment" doim qo'shiladi.
- Legacy SMC: FVG `filled` doim False; BOS eskirgan bo'lishi mumkin.
- `RiskCalculator.position_size` 0.01 lotga yuqoriga yaxlitlaydi (legacy yo'l uchun).
- `SECRET_KEY` default qiymatga o'xshaydi — almashtiring.
- Testlar umumiy in-memory DB ishlatadi va bir-biridan izolyatsiyalanmagan.

**Kerakli ma'lumotlar:**
- Brokerdan real spread tarixi (sessiyalar bo'yicha), komissiya va XAUUSD spetsifikatsiyasi.
- Tarixiy iqtisodiy kalendar — news filtrini backtest qilish uchun.
- Bear yoki yon bozor davrlari — SELL tomonini va trenddan tashqari xatti-harakatni tekshirish
  uchun.

**Demo sinovi:**
- Har bir signal audit logidan olinadi. Qayd etiladi: haqiqiy kirish narxi, spread va slippage,
  natija (R).
- Xuddi shu davr uchun backtest bilan solishtiriladi.
- Chastota ~1.5/oy bo'lgani uchun 6 oyda ~9 savdo bo'ladi. Bu faqat bajarilishdagi xatolarni
  (narx manbai, spread, vaqt) aniqlashga yetadi, edge'ni tasdiqlashga yetmaydi.

**Real savdodan oldin talab qilinadigan dalillar:**
- ≥ 100 ta OOS savdo (walk-forward + forward/demo) bo'yicha xarajatlardan keyingi expectancy
  ishonch oralig'ining pastki chegarasi > 0.
- Bear yoki yon bozorni o'z ichiga olgan davrda barqarorlik.
- Real broker spread'i bilan qayta hisob.
- Demo natijalarining backtest taqsimotidan statistik farq qilmasligi.

Bu shartlar bajarilmaguncha tizimni faqat qaror qabul qilishda yordamchi vosita sifatida
ishlating.
