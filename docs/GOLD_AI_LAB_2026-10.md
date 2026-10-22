# Gold_AI — tadqiqot laboratoriyasi, paper trading va real savdoga tayyorlik (2026-10-22)

> Avvalgi bosqich (audit, v2 dvigatel, backtest): [GOLD_AI_AUDIT_2026-10.md](GOLD_AI_AUDIT_2026-10.md).
> Bu hujjat uning davomi. Barcha raqamlar `docs/research/` dagi JSON fayllardan olingan va
> `scripts/research/` dagi skriptlar bilan qayta hisoblanishi mumkin.
> Git: `gold-ai-v2` branch.

## 1. Dastlabki arxitektura va audit (qisqacha)

Batafsil audit oldingi hujjatda. Bu bosqichda tekshirilgan qo'shimcha masalalar:

- **Broker integratsiyasi.** `src/market_data/mt4_connector.py`, `mt5_connector.py` va
  `mt4/GoldAI_Bridge.mq4` faqat narx uzatadi. Kod bazasida order ochish yoki yopish funksiyasi
  **umuman yo'q**. Shu holat test bilan qotirildi (`test_no_order_execution_code_in_backend`).
- **Demo/paper infratuzilma** mavjud emas edi — yangidan yaratildi (6-bo'lim).
- **ML komponenti** (RandomForest) tekshirildi: bashorat qobiliyati yo'q (5-bo'lim).
- **Twelvedata so'rov byudjeti.** Scheduler 5 daqiqada H1/H4/D1'ni yangilab, kuniga ~864 so'rov
  qilardi. Free tier limiti ~800/kun. Byudjet qayta taqsimlandi (taxminan ~624/kun).

**Saqlanadigan komponentlar:** FastAPI/PostgreSQL arxitekturasi, Twelvedata ma'lumot zanjiri,
Telegram, frontend, `strategy/` v2 dvigatel.

**Almashtirilgan yoki chetlatilgan komponentlar:**
- legacy vaznli ball (`SIGNAL_ENGINE=legacy` orqali hali ham tanlash mumkin);
- ML va kalit so'zli news sentimenti qarordan chetlatilgan;
- `gold_ai_engine` faqat ma'lumot uchun qoladi.

## 2. Muammolar va dalillar (yangi)

| Muammo | Dalil | Holat |
|---|---|---|
| Mavjud RF modelining bashorat qobiliyati yo'q | Walk-forward (H4, 2022–2026, 7 137 namuna, 5 sham purge): balanced accuracy 0.335 (tasodif 0.333); aniqlik 0.448, majority-class baseline'dan past | Qarorga ta'sir qilmaydi; UI'da "ML score" ko'rsatkichi ma'nosiz |
| Barcha strategiyalarda SELL tomoni salbiy | Laboratoriya, 2021–2026: trend_pullback SELL −0.16R (17), donchian SELL −0.25R (101), squeeze SELL −0.13R (61) | Ochiq **gipoteza** (7-bo'lim) |
| Rejim router murakkabligi o'zini oqlamadi | H4 router walk-forward +0.20R (114) — oddiy trend_pullback dan yaxshi emas | Router ishlatilmaydi |
| Kunlik so'rov limiti oshib ketgan | Scheduler kodida 3 ta TF × 288 marta/kun | Tuzatildi (`CANDLE_REFRESH_MINUTES=15`) |
| Swap xarajati hisobga olinmagan | H4 savdolar bir necha kecha ochiq turadi | Simulyatorga qo'shildi (broker qiymati noma'lum) |

## 3. O'zgartirilgan fayllar va funksiyalar

| Fayl | Mazmuni |
|---|---|
| `backend/strategy/lab.py`, `run_lab.py` | 5 strategiya oilasi, bitta harness'da. Train'da o'rgatilgan rejim-router va uning walk-forward testi |
| `backend/strategy/backtest.py` | MFE/MAE, swap (21:00 UTC rollover, chorshanba ×3), bootstrap CI. Umumiy `fill_price`/`step_exit` — backtest va paper bitta qoidada ishlaydi |
| `backend/strategy/news_study.py` | NFP/CPI/FOMC atrofida event study; FOLLOW/FADE qoidalari; blackout testi |
| `backend/strategy/health.py` | Strategiya salomatligi: OK / DEGRADED (risk ×0.5) / SUSPENDED (NO TRADE) |
| `backend/strategy/registry.py` | Versiyalangan reestr: champion/candidate/retired, `compare`, `promote` (faqat qo'lda), `rollback` |
| `backend/strategy/learning.py` | Savdodan keyingi tahlil → gipotezalar. Strategiyani o'zi o'zgartirmaydi |
| `backend/paper/broker.py`, `service.py`; `backend/models/paper.py`; `alembic/versions/0006_paper_trading.py` | Paper trading: virtual hisob, idempotent submit, M5 tick, hisob limitlari |
| `backend/execution/gate.py` | Rejimlar: signal_only/paper. Live doim bloklangan; `BrokerAdapter` interfeysi bor, lekin implementatsiyasi yo'q |
| `backend/services/signal_cycle.py` | API va scheduler uchun yagona v2 sikli (dedup → DB → paper → alert) |
| `backend/services/scheduler.py` | Har soat :03 da signal sikli, har 5 daqiqada paper tick, so'rov byudjeti |
| `backend/routers/paper.py` | `GET /api/v1/paper/stats`, `/paper/trades`, `/paper/analysis`, `/execution/readiness`, `/strategy/registry` |
| `backend/strategy/live.py` | Health holatiga ko'ra signalni bloklaydi yoki riskni kamaytiradi; champion konfiguratsiyasi ishlatiladi |
| `backend/main.py` | Paper jadvallari (additive); startup'da reestr seed qilinadi |
| `scripts/research/*` | Tarix va M1 yuklash, makro hodisalar ro'yxatini qurish, ML baholash |

## 4. Test natijalari

| Test | Natija |
|---|---|
| To'liq to'plam | **205 o‘tdi, 2 yiqildi.** Yiqilganlar — oldingi hisobotdagi o'sha 2 ta oldindan mavjud xato; signal zanjiriga aloqasi yo'q |
| `tests/test_paper_and_learning.py` | 21/21 o'tdi: paper fill/zona/muddat/SL-first/vaqt/gap, backtest paritet, idempotentlik, limitlar, health, registry (promote rad etish, rollback), learning, live gate, "order kodi yo'q" guard, lab darajalari, endpoint'lar |
| `tests/test_strategy_v2.py` | 47/47 o'tdi |
| Real ma'lumotda paper ↔ backtest paritet | 42 ta test savdosining **42 tasi** paper-broker orqali qayta o'ynalganda aynan bir xil chiqish sababi va R berdi |
| Refaktoringdan keyingi regression | v2 test davri: 42 savdo, +0.492R — o'zgarishsiz |
| Real vaqtdagi paper trading | **Bajarilmadi** — server yangi kod bilan deploy qilinmagan |

## 5. Strategiyalarni bir xil sharoitda taqqoslash

**Umumiy shartlar.**
- Ma'lumot: Twelvedata XAU/USD, tozalangan.
- Xarajatlar: spread $0.30, slippage $0.10 (har bir fill) — taxminiy qiymatlar.
- Bajarilish: kirish keyingi sham open'ida; bir sham ichida SL va TP ikkalasiga tegilsa → SL;
  bir vaqtda faqat bitta pozitsiya.
- Parametrlar oldindan belgilangan (grid search yo'q).
- H4/D1: train 2021-01…2024-06, test 2024-07…2026-10.

| Strategiya (H4/D1) | Train: savdo / expectancy | Test: savdo / expectancy (CI95) | Test PF | Test max DD | Savdo/oy |
|---|---:|---:|---:|---:|---:|
| **trend_pullback (v2 champion)** | 44 / +0.36R | 42 / **+0.49R** [0.00; 0.99] | 1.92 | 3.0% | 1.2 |
| donchian_break | 172 / −0.09R | 121 / +0.31R [0.05; 0.56] | 1.57 | 3.3% | 4.2 |
| ts_momentum | 46 / −0.03R | 36 / −0.26R [−0.65; 0.21] | 0.65 | 8.1% | ~1 |
| mean_reversion | 2 / — | 0 / — | — | — | ≈0 |
| squeeze_break | 78 / −0.23R | 61 / +0.46R [0.03; 0.86] | 1.83 | 5.5% | 2.0 |
| Rejim router (train'da o'rgatilgan) | — | 42 / +0.61R; **walk-forward 114 / +0.20R** | | | |

**H1/H4 da** (test 2025-04…2026-10) barcha strategiyalar ≈ 0: −0.003R dan +0.14R gacha, CI
nolni o'z ichiga oladi. Router walk-forward −0.04R.

**Xulosalar.**
- Train **va** test davrlarining ikkalasida musbat bo'lgan yagona strategiya — `trend_pullback`.
- Breakout strategiyalari train'da (2021–24) salbiy, test'da (2024–26 bull bozori) musbat.
  Ular bozor rejimiga bog'liq va hozirgi holatda ishonchsiz.
- Mean-reversion oldindan belgilangan qoidalar bilan deyarli signal bermadi, shuning uchun uni
  baholab bo'lmaydi.
- Rejim router murakkabligi o'zini oqlamadi. Oddiy champion saqlandi.
- **Swap sezgirligi** (test): −$0.25/oz/kecha → trend_pullback +0.47R; −$0.50 → +0.44R.
  Real broker swap qiymati noma'lum.
- **Xarajatdan keyingi champion statistikasi** (test): win rate 45.2%, PF 1.92, o'rtacha foyda
  +2.28R, o'rtacha zarar −0.98R, maksimal ketma-ket zarar 6. O'rtacha MFE 1.60R, MAE 0.96R
  (router test natijasidan; uning savdolari champion bilan deyarli bir xil).

## 6. Tarixiy trend va yangiliklar bo'yicha xulosalar

**Rejimlar** (H4, 2021–2026, keyingi 6 shamdagi harakat ATR birligida):
- Barcha rejimlarda yuqoriga harakat ulushi 52–56%. Hatto TREND_DOWN rejimida ham o'rtacha
  harakat +0.11 ATR. Bu davr kuchli secular o'sish davri bo'lgan.
- HIGH_VOLATILITY rejimi kam uchraydi (1.5%). Absolyut harakat eng katta (1.6 ATR), o'rtachasi
  esa salbiy — bu rejimda NO TRADE qoidasini qo'llab-quvvatlaydi.

**Sessiyalar** (trend_pullback, H4, to'liq davr):
- London–NY overlap: +1.03R (n=17).
- Asia: +0.41R (n=42).
- London va NY-late: ≈ +0.07R.
- Har bir guruhda savdolar kam (<50), shuning uchun filtr sifatida qo'llanmadi.

**Yangiliklar** (151 ta hodisa: 57 CPI, 38 FOMC, 56 NFP; 2022-01…2026-10).
- **Manbalar va vaqt:**
  - sanalar bls.gov arxivi va federalreserve.gov taqvimidan olingan;
  - notation vote'lar chiqarib tashlangan;
  - vaqtlar 08:30 / 14:00 ET, DST bilan UTC'ga o'tkazilgan;
  - narx — Twelvedata M1.
  - Ro'yxat: `docs/research/macro_events_2022_2026.csv`.
- **Look-ahead himoyasi:** asos narx — e'londan oldingi sham close'i. Qoidalar faqat e'londan
  keyin ma'lum bo'lgan narxni ishlatadi (+5 daqiqadan boshlab).
- **Volatillik** — eng ishonchli natija. 15 daqiqalik 1-daqiqalik diapazon 4.9–5.4× kengayadi.
  Birinchi 5 daqiqadagi eng katta 1-daqiqalik sham (median): CPI $10.8, NFP $9.9, FOMC $7.6.
- **Yo'nalish:**
  - NFP: barqaror yo'nalish yo'q, har bir ufqda CI nolni o'z ichiga oladi.
  - FOMC: barqaror yo'nalish yo'q; +60 daqiqadagi o'rtacha yillar bo'yicha ishorasini
    o'zgartiradi (2022 +6.6 → 2026 −18.7).
  - CPI: +1…+15 daqiqada o'rtacha +$3.7…4.8, 60–68% holatda yuqoriga, CI noldan yuqori. Lekin
    21 ta parallel test o'tkazilgan; +60 daqiqada natija yillar bo'yicha beqaror (2024 −2.1,
    2026 +11.6); surprise (prognoz) ma'lumoti yo'q. **Gipoteza, qoida emas.**
- **Impuls va keyingi harakat:** CPI va FOMC'da impuls davom etish ulushi ~50–55%, NFP'da 45%.
- **Savdo qoidalari** (taxminiy yangilik xarajati $1.50/oz):
  - FOLLOW: −$0.85/oz (n=151);
  - FADE: −$2.15/oz.
  - Ikkalasi ham train va test davrlarida salbiy. **Yangilik atrofida savdo qilish qoidasi
    tasdiqlanmadi.**
- **v2 blackout:**
  - ±30 daqiqalik qoida H4 strategiyaga deyarli ta'sir qilmaydi (80 savdodan 1 tasi).
  - Kirishdan keyingi 24 soatda yirik hodisa bo'lgan savdolar +0.15R (n=12, CI [−0.73; 1.03]),
    qolganlari +0.60R. Farq ehtimoliy, lekin n juda kichik — forward tekshiruv kerak.
- **Yangilik vaqtidagi spread** tarixiy ma'lumoti yo'q. Natijalardagi 3× spread taxminiy.

## 7. Demo/paper trading natijalari

**Real vaqtdagi paper savdo natijalari yo'q.** Infratuzilma tayyor va testdan o'tgan, lekin
server yangi kod bilan ishga tushirilmagan. Deploy'dan keyin quyidagicha ishlaydi:

- **Har soat :03 da** v2 qaror qabul qilinadi. Yangi BUY/SELL signal PENDING paper savdoga
  aylanadi. Bir yopilgan sham uchun faqat bitta savdo ochiladi: `signal_key` unique, shuning
  uchun API va scheduler bir xil signalni ikki marta ocholmaydi.
- **Har 5 daqiqada** yopilgan M5 shamlar bo'yicha fill, SL/TP va vaqt bo'yicha chiqish
  hisoblanadi. Qoidalar backtest bilan bir xil (paritet tasdiqlangan).
- **Ma'lumot eskirgan bo'lsa,** pozitsiya oxirgi yopilgan shamgacha yuritiladi va hech narsa
  taxmin qilinmaydi. Bar oralig'ida uzilish bo'lsa, savdoga `data_gap` belgisi qo'yiladi.
- **Hisob limitlari:**
  - 1 ta ochiq pozitsiya;
  - kunlik zarar −2%;
  - peak'dan drawdown −10% → yangi kirishlar to'xtaydi (HALT).
- **Har bir savdo uchun yoziladi:** vaqt, strategiya va konfiguratsiya versiyasi, rejim,
  sabablar va score komponentlari, entry/SL/TP, fill va chiqish narxi, R, $ natija, xarajatlar,
  MFE/MAE, davomiylik.
- **Paper hisob real hisobdan ajratilgan:**
  - `mode="paper"` dan boshqa hisobga servis ishlamaydi;
  - real hisob modeli umuman yo'q.

**Kutilgan chastota** ~1.2–1.5 savdo/oy. 6 oyda ~8 savdo bo'ladi. Bu faqat bajarilishdagi
xatolarni topishga yetadi, edge'ni tasdiqlashga yetmaydi.

## 8. O'rganish mexanizmi va model versiyalari

**Sikl:** kuzatuv (paper savdolari, `GET /paper/analysis`) → gipoteza (`learning.analyse`,
kamida 20–50 savdo talab qiladi) → `research.py`/`run_lab.py` da train → OOS + walk-forward →
`registry register` (candidate) → `registry compare`. Champion bilan bir xil ma'lumot
fingerprint'ida solishtiriladi. Mezonlar:
- test savdolari ≥30;
- walk-forward savdolari ≥60;
- CI95 pastki chegarasi >0;
- walk-forward expectancy champion'nikidan yuqori;
- drawdown champion'nikidan ≤1.5×.

So'ng **qo'lda** `promote --by <ism>` → paper → health monitor. Muammo bo'lsa `rollback`.

**Avtomatik o'zgartirish yo'q.**
- `promote` mezonlarga javob bermagan candidate'ni rad etadi.
- `--force` faqat yozma sabab bilan ishlaydi.
- Health monitor strategiyani faqat cheklashi yoki to'xtatishi mumkin. Qayta yoqish — inson
  qarori.

**Versiyalar:**
- Champion: `v2.0.0-<config_hash>` (startup'da seed qilinadi).
- Har bir signal va paper savdo `strategy_version` hamda `config_hash` ni saqlaydi.

**Murakkab ML, bandit va RL qo'llanmadi.** Sababi:
- chastota oyiga ~1.5 savdo;
- mavjud RF bashorat qobiliyatini ko'rsatmadi.

Bunday usullar uchun yuzlab mustaqil savdo kerak. **Model o'rganishga tayyor emas:**
ma'lumot yetarli emas.

## 9. Xarajatlardan keyingi statistika (champion)

| Ko'rsatkich | Train 2021-01…2024-06 | Test 2024-07…2026-10 | Walk-forward OOS |
|---|---:|---:|---:|
| Savdolar | 44 | 42 | 120 |
| Win rate | 40.9% | 45.2% | — |
| Profit factor | 1.59 | 1.92 | — |
| Expectancy | +0.36R | +0.49R (CI95 0.00…0.99) | +0.27R |
| Max DD (0.5% risk) | 3.1% | 3.0% | — |
| Xarajatlar (bitta savdoga) | 0.03R | 0.016R | — |

Tasodifiy nazorat natijalari (oldingi hisobot): D1 trend UP bo'lganda tasodifiy long'lar test'da
+0.39R berdi, ularning 32% champion'dan yaxshi. Edge'ning asosiy qismi D1 trend filtridan va
2021–2026 bull bozoridan kelyapti.

## 10. Qolgan muammolar va ma'lumotga ehtiyoj

**Ma'lumotlar:**
- Real broker spread va swap'i, ayniqsa yangiliklar vaqtidagi spread.
- XAUUSD spetsifikatsiyasi.
- Konsensus prognozlar (surprise tahlili uchun).
- Bear yoki yon bozor davrlari.

**Ochiq muammolar:**
- SELL tomoni gipotezasini forward davrda tekshirish kerak. Uni bitta namunada tanlab o'chirish
  data snooping bo'ladi.
- Bazadagi begona seriyani tozalash (skript tayyor, qo'llanmagan).
- Deploy qilinmagan.
- Frontend yangi endpoint'larni ko'rsatmaydi.
- `SECRET_KEY` default qiymatga o'xshaydi.
- 2 ta oldindan mavjud test xatosi.

**Real savdo infratuzilmasida yetishmaydiganlar:**
- `BrokerAdapter` implementatsiyasi;
- order holati noaniqligini boshqarish;
- favqulodda `close_all`;
- monitoring va alerting.

## 11. Real hisobga tayyorlik

**Daraja: tayyor emas.** Real savdo kod darajasida bloklangan:
- `execution/gate.py` da broker adapteri yo'q;
- `TRADING_MODE=live` xavfsiz `signal_only` rejimiga qaytadi.

`GET /api/v1/execution/readiness` qaysi tekshiruvlar o'tmaganini ko'rsatadi:

| Talab | Holat |
|---|---|
| Broker adapteri yozilgan va tekshirilgan | ✗ |
| ≥100 yopilgan paper savdo, ≥180 kun | ✗ (0) |
| Paper expectancy CI95 pastki chegarasi > 0 (real xarajatlar bilan) | ✗ |
| Strategiya salomatligi OK | ✗ (ma'lumot yo'q) |
| Imzolangan rozilik fayli (account_id + risk konfiguratsiyasi xeshi) | ✗ |
| Risk limitlari (per-trade %, kunlik/umumiy DD, max pozitsiya) | ✓ konfiguratsiyada |

Joriy chastotada 100 ta paper savdo to'planishi taxminan 6–7 yil oladi. Bu muddatni qisqartirish
uchun champion bilan **mustaqil** bo'lgan qo'shimcha strategiyalarni topish kerak. Har biri
yuqoridagi registry jarayonidan o'tishi shart.

## Ishga tushirish

```bash
# testlar
DATABASE_URL=sqlite:///./t.db python -m pytest -q tests/

# tadqiqotlarni qayta hisoblash (backend/ papkasidan)
python -m strategy.run_lab --h1 td_1h.csv --h4 td_4h.csv --now 2026-10-22T07:00:00 --out lab.json
python -m strategy.news_study --events ../docs/research/macro_events_2022_2026.csv --m1 m1/ \
    --h4 td_4h.csv --now 2026-10-22T07:00:00 --out news.json

# reestr
python -m strategy.registry list | compare <id> | promote <id> --by "<ism>" | rollback --by "<ism>"

# deploy (sizning qaroringiz)
docker compose build backend && docker compose up -d backend

# paper holati
curl localhost:8001/api/v1/paper/stats
curl localhost:8001/api/v1/execution/readiness
```

**Yangi env o'zgaruvchilari:**
- `PAPER_TRADING_ENABLED` (default true)
- `PAPER_START_BALANCE=10000`
- `PAPER_MAX_OPEN=1`
- `PAPER_DAILY_LOSS_PCT=2`
- `PAPER_MAX_DD_PCT=10`
- `SIGNAL_CYCLE_ENABLED` (default true)
- `SIGNAL_CYCLE_ALERTS` (default false — avtomatik sikl Telegram'ga yozmaydi)
- `CANDLE_REFRESH_MINUTES=15`
- `TRADING_MODE` (`signal_only` | `paper`)
- `GOLDAI_SWAP_LONG` / `GOLDAI_SWAP_SHORT` (USD/oz/kecha)
- `STRATEGY_REGISTRY_DIR`
