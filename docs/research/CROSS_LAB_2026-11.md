# Boshqa instrumentlar va pasayuvchi bozor laboratoriyasi (2026-11-18)

**Xulosa:** 16 ta test o'tkazildi (4 strategiya × 4 instrument). **Ularning birortasi ham oldindan belgilangan qabul mezonlaridan o'tmadi.** Ikki va undan ortiq instrumentda ishlaydigan "robust" strategiya topilmadi. Paper yoki shadow rejimiga yangi strategiya qo'shilmaydi.

- Kod: `backend/strategy/cross_lab.py`. Protokol shu fayl boshida, natijalarni ko'rishdan oldin yozilgan.
- To'liq natijalar: `docs/research/cross_lab.json`.

## Nima tekshirildi

**Instrumentlar.** Twelvedata, H1 + H4, 2020-01 … 2026-11. Ma'lumot sifati hamma instrument uchun OK.

| Instrument | Spread | Slippage |
|---|---|---|
| XAUUSD | $0.30 | $0.10 |
| EURUSD | 1.0 pip | 0.2 pip |
| GBPUSD | 1.2 pip | 0.2 pip |
| USDJPY | 1.0 pip | 0.2 pip |

- FX narxlari pip birligiga o'tkazildi. Sababi: engine SL/TP darajalarini 2 xona aniqlikda yaxlitlaydi. R natijalar narx masshtabiga bog'liq emas — bu test bilan tasdiqlangan.
- XAGUSD (kumush) Twelvedata'ning bepul tarifida mavjud emas, shuning uchun tekshirilmadi.
- Swap = 0 (noma'lum), avvalgi barcha tadqiqotlardagidek.

**Strategiyalar.** Parametrlar oldingi tadqiqotlardagidek muzlatilgan, o'zgartirilmagan:

| Strategiya | Timeframe | Manba |
|---|---|---|
| `trend_pullback` (champion) | H4 / D1 | v2 engine |
| `donchian_break` | H4 / D1 | lab.py |
| `squeeze_trend` | H1 / D1 | vol_lab.py |
| **`range_fade`** (yangi) | H1 / D1 | Pasayuvchi va yon bozor gipotezasi: lab.py'dagi mean-reversion qoidasi, faqat D1 trendi yo'q paytda |

**Qabul mezonlari** (avvalgi laboratoriya bilan bir xil, hammasi bajarilishi shart):
1. test davrida ≥ 30 savdo;
2. test expectancy CI95 pastki chegarasi > 0;
3. train expectancy > 0;
4. test natijasi tasodifiy nazoratning 90-persentilidan yuqori;
5. test max drawdown ≤ 6%.

"Robust" — strategiya kamida 2 ta instrumentda qabul qilingan bo'lishi kerak. 16 ta test o'tkazilganda tasodifan ~1 tasi o'tib ketishi kutiladi, shuning uchun bitta instrumentdagi muvaffaqiyat yetarli emas.

## Natijalar (test davri)

| Strategiya | XAUUSD | EURUSD | GBPUSD | USDJPY | 4 instrument birgalikda |
|---|---:|---:|---:|---:|---:|
| `trend_pullback` | +0.47R (n=45) | −0.08R (41) | −0.27R (28) | +0.08R (27) | +0.09R [−0.17; 0.34] |
| `donchian_break` | +0.35R (126) | +0.20R (112) | −0.10R (120) | −0.24R (123) | +0.05R [−0.08; 0.18] |
| `squeeze_trend` | +0.38R (145) | −0.02R (86) | −0.01R (84) | −0.03R (116) | +0.11R [−0.04; 0.27] |
| `range_fade` | 0 savdo | 1 | 1 | 1 | 3 ta savdo — baholab bo'lmaydi |

- **Oltindan tashqarida ishlamadi.** Uchala trend strategiyasi FX'da test davrida ≈ 0 yoki manfiy natija berdi.
- **Oltindagi musbat natijalar ham yetarli emas.** Ular mezonlardan biriga to'qnashdi: train davri manfiy yoki tasodifiy nazoratdan yaxshi emas.
- **Champion'ning CI95'i endi 0 ni ham o'z ichiga oladi:** [−0.03; 0.95]. Yangi ma'lumotlar qo'shilgandan keyin natija statistik ishonchli emas.

### D1 trendiga qarab natijalar (2020–26, train + test)

| Strategiya / instrument | D1 UP | D1 DOWN |
|---|---:|---:|
| `trend_pullback` XAUUSD | +0.59R (72) | +0.07R (20) |
| `squeeze_trend` XAUUSD | +0.18R (201) | −0.19R (48) |
| `donchian_break` XAUUSD | +0.45R (124) | −0.22R (34) |
| `donchian_break` USDJPY | +0.35R (129) | −0.42R (30) |
| `squeeze_trend` USDJPY | +0.14R (211) | +0.01R (47) |

Natija faqat **kuchli o'sish trendidagi instrumentlarda** musbat chiqadi: oltin 2024–26 da, USDJPY 2021–24 da. Pasayish trendida va trendsiz bozorda natija ≈ 0 yoki manfiy. Bu oltinning hozirgi holatiga (D1 DOWN) to'g'ridan-to'g'ri tegishli.

### `range_fade` — gipotezani tekshirib bo'lmadi
Muzlatilgan qoidalar birdaniga to'rtta shartni talab qiladi: RANGE rejimi, D1 trendi yo'q, Bollinger chegarasidan chiqish va RSI ekstremumi. Bu shartlar deyarli hech qachon bir vaqtda bajarilmaydi — 6.8 yilda 0–3 ta savdo. Shartlarni yumshatish yangi, alohida protokol bilan bo'lishi kerak. Bu natijalarni ko'rib turib parametr o'zgartirish data snooping (natijaga moslab sozlash) bo'ladi.

## Umumiy xulosa (barcha tadqiqotlar bo'yicha)

Oktabr va noyabrdagi laboratoriyalarda ~25 ta strategiya × instrument × davr kombinatsiyasi tekshirildi. Natija bir xil:
- **Oddiy texnik qoidalar faqat "kuchli trend bo'yicha savdo"dan foyda oladi.** Bu edge strategiyaning o'zidan emas, bozor rejimidan keladi. Trend bo'yicha tasodifiy kirishlar ham shunga yaqin natija beradi.
- **Rejim o'zgarganda edge yo'qoladi,** va buni oldindan bilib bo'lmaydi.
- **Hozir oltinda D1 trendi DOWN.** Champion bu holatda tarixan ≈ 0 natija bergan (+0.07R, 20 ta savdo). Paper va shadow natijalari buni real vaqtda tekshiradi.

## Tavsiyalar
1. **Real pulga o'tmaslik.** Mavjud signallarni yuqori daromad manbai deb hisoblamaslik kerak.
2. **Paper va shadow kuzatuvni davom ettirish.** Ular arzon va halol forward ma'lumot beradi.
3. **Broker xarajatlarini yig'ish** (`docs/BROKER_COST_FEED.md`). Real spread va swap bilan edge yanada kichrayishi mumkin.
4. Agar yangi edge izlanadigan bo'lsa, oddiy TA o'rniga **boshqa ma'lumot manbalariga** e'tibor qaratish kerak:
   - makro surprise (konsensus prognoz bilan haqiqiy natija farqi);
   - real yield va DXY;
   - pozitsionlash (COT hisobotlari).

   Har biri oldindan yozilgan protokol va tasodifiy nazorat bilan tekshirilishi shart.
