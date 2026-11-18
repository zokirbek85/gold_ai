# Broker spread/swap ma'lumotini yig'ish (MetaTrader EA)

## Nima uchun kerak

Backtest, paper savdo va lot hisoblash hozircha **taxminiy** xarajatlardan foydalanadi:
- spread — $0.30;
- slippage — $0.10;
- swap — 0 (bu "bepul" degani emas, "noma'lum" degani).

Real broker'ingiz spread va swap'i boshqacha bo'lsa, barcha natijalar va R hisoblari noto'g'ri chiqadi. Ayniqsa yangiliklar va rollover paytida farq katta bo'ladi.

`GoldAI_CostFeed` EA broker'dagi spread va swap ma'lumotlarini har daqiqada backend'ga yuboradi. **EA savdo qilmaydi:** buyurtma ochmaydi, o'zgartirmaydi va yopmaydi.

## O'rnatish

### 1. EA faylini nusxalash
MetaTrader'da **File → Open Data Folder** ni oching va faylni quyidagi papkaga nusxalang:

| Terminal | Fayl | Papka |
|---|---|---|
| MT4 | `mt4/GoldAI_CostFeed.mq4` | `MQL4/Experts/` |
| MT5 | `mt5/GoldAI_CostFeed.mq5` | `MQL5/Experts/` |

Keyin MetaEditor'da faylni oching va **Compile** (F7) tugmasini bosing.

### 2. WebRequest'ga ruxsat berish
**Tools → Options → Expert Advisors** bo'limida:
- "Allow WebRequest for listed URL" ni belgilang;
- ro'yxatga `http://127.0.0.1:8001` manzilini qo'shing.

MetaTrader boshqa kompyuterda yoki virtual mashinada ishlasa, `127.0.0.1` o'rniga Mac'ning lokal IP manzilini yozing (masalan `http://192.168.1.10:8001`).

### 3. EA'ni grafikka qo'yish
EA'ni istalgan grafikka qo'ying va parametrlarni kiriting:

| Parametr | Qiymat |
|---|---|
| `FeedToken` | `gold_ai/.env` faylidagi `BROKER_FEED_TOKEN` qiymati |
| `Symbols` | Broker'dagi nomlar. Agar oltin `GOLD` deb atalsa: `GOLD=XAUUSD`. Kumush ham kerak bo'lsa: `GOLD=XAUUSD,SILVER=XAGUSD` |
| `BackendURL` | Odatda o'zgartirish shart emas |

### 4. AutoTrading'ni yoqish
"AutoTrading" tugmasi yoniq bo'lishi kerak, aks holda EA ishlamaydi. EA baribir savdo qilmaydi.

### 5. Ishlayotganini tekshirish
Bir necha daqiqadan keyin quyidagi so'rovni bajaring:
```bash
curl -s "localhost:8001/api/v1/broker/costs?symbol=XAUUSD" | python3 -m json.tool
```
Javobdagi `minutes` qiymati oshib borishi kerak. MetaTrader'ning **Experts** jurnalida xato xabarlari ko'rinadi.

## Hisobot (`GET /api/v1/broker/costs`)

| Bo'lim | Mazmuni |
|---|---|
| `spread.normal_hours` | Oddiy soatlardagi spread: p50, p90, p99 |
| `spread.rollover_21_23_utc` | Kunlik rollover paytidagi spread |
| `spread.news_pm15min_max` | Yuqori ta'sirli USD yangiliklaridan ±15 daqiqa ichidagi eng katta spread |
| `spread.by_utc_hour_p50` | Har bir UTC soat uchun spread medianasi |
| `spec` | Kontrakt hajmi, swap (broker formatida va $/oz/kecha'ga o'girilgan), uch karra swap kuni |
| `suggested_env` | `.env` ga yozish mumkin bo'lgan qiymatlar: `GOLDAI_SPREAD`, `GOLDAI_SWAP_LONG`, `GOLDAI_SWAP_SHORT`, `GOLDAI_CONTRACT_SIZE` |

**Qiymatlar avtomatik qo'llanmaydi.** Xarajatlar barcha natijalarga ta'sir qiladi, shuning uchun qarorni siz qabul qilasiz. Qo'llash uchun:
- kamida 2 hafta ma'lumot yig'ing;
- tavsiya etilgan qiymatlarni `.env` ga yozing;
- `docker compose up -d backend` buyrug'ini bajaring.

## Cheklovlar
- **Demo va real hisob farqi.** Demo hisob spread'i real hisobnikidan farq qilishi mumkin. Hisobotda `is_demo` maydoni buni ko'rsatadi.
- **Valyuta.** Swap'ni o'girishda hisob valyutasi USD deb olinadi.
- **Slippage o'lchanmaydi.** Uni faqat haqiqiy buyurtmalar orqali o'lchash mumkin.
- **Spread o'lchami.** Spread har soniyada bir marta tekshiriladi. Tick'lar orasidagi juda qisqa sakrashlar ko'rinmasligi mumkin.
