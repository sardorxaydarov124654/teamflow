# TeamFlow — kompaniyalar uchun multi-tenant loyiha va vazifalar boshqaruvi platformasi

## Loyihaning maqsadi

**TeamFlow** — bir nechta kompaniya (tenant) jamoalariga bitta tizim ichida
**loyihalar, vazifalar va xodimlarni** boshqarish imkonini beradigan SaaS platforma.
Har bir kompaniya o'zining alohida, boshqalardan to'liq ajratilgan ish muhitida ishlaydi.

### Qanday muammolarni hal qiladi

- **Ma'lumotlar aralashib ketishi** — tenant isolation: Company A foydalanuvchisi Company B ning
  loyiha, vazifa va a'zolarini ko'ra olmaydi (queryset filtering + object-level tekshiruv).
- **Ishlar turli joyda tarqalib ketishi** — loyihalar, vazifalar, izohlar va muddatlar yagona joyda.
- **Kim nima uchun mas'ul ekanini bilmaslik** — assignment, priority, status va deadline.
- **Muhim o'zgarishlarni o'tkazib yuborish** — bildirishnomalar bazada saqlanadi va WebSocket orqali
  real vaqtda yetkaziladi.
- **Deadline'larni qo'lda kuzatish** — Celery Beat har 15 daqiqada muddati yaqinlashgan vazifalar
  haqida eslatma yuboradi.
- **Statistikani qayta-qayta hisoblash** — dashboard ko'rsatkichlari Redis'da qisqa muddat cache qilinadi.

### Kimga foyda beradi

| Rol | Imkoniyatlari |
| --- | --- |
| **Platform Admin** | Butun platformani boshqaradi, barcha kompaniyalarni ko'radi, kompaniyani bloklaydi/blokdan chiqaradi. |
| **Manager** | O'z kompaniyasida loyiha va vazifalarni yaratadi/tahrirlaydi/o'chiradi, a'zolarni taklif qiladi, rollarni boshqaradi, tarifni o'zgartiradi. |
| **Employee** | Kompaniya loyiha va vazifalarini ko'radi, o'ziga biriktirilgan vazifalar holatini yangilaydi, izoh qoldiradi, bildirishnoma oladi. |

Obuna rejalari: **Free** ($0: 3 a'zo / 5 loyiha), **Pro** ($29: 50 a'zo / cheksiz loyiha), **Max** ($99: cheksiz).

### To'lov oqimi (mock)

- Landing'dagi narxlar kartasidagi tugma tanlangan tarifni ro'yxatdan o'tish sahifasiga olib boradi (`/accounts/register/?plan=pro`).
- **Free** tanlansa karta so'ralmaydi. **Pro / Max** tanlansa karta raqami, karta egasi, amal qilish muddati (MM/YY) va CVV majburiy (Luhn va muddat tekshiriladi), shundan keyingina akkaunt yaratiladi.
- Xavfsizlik: bazaga faqat brend, oxirgi 4 raqam, ism va muddat yoziladi. To'liq raqam va CVV hech qayerda saqlanmaydi. To'lov haqiqiy emas (pul yechilmaydi).
- **Billing** bo'limi (sidebar'dagi Billing va "Upgrade plan") faqat **Pro** va **Max** ni ko'rsatadi: joriy tarif belgilanadi, boshqasi "Upgrade to…" (Free'dan) yoki "Switch to…" (Pro ↔ Max) tugmasi bilan taklif qilinadi. Saqlangan karta bilan almashtirish bir bosishda bajariladi; karta bo'lmasa so'raladi.
- Joriy foydalanish yangi tarif limitidan oshsa (masalan, Max → Pro, a'zolar 50 dan ko'p) almashtirish bloklanadi.

## Sayt sahifalari

| Bo'lim | Manzil |
| --- | --- |
| Landing page (ro'yxatdan o'tmaganlar uchun) | `/` |
| Kirish / Ro'yxatdan o'tish | `/accounts/login/`, `/accounts/register/` |
| Dashboard (statistika, grafik, kalendar, faoliyat, resurslar) | `/dashboard/` |
| Loyihalar (ro'yxat, yaratish, tahrirlash, o'chirish) | `/projects/` |
| Vazifalar (filtr, qidiruv, izohlar, status o'zgartirish) | `/tasks/` |
| Kalendar | `/tasks/calendar/` |
| Hisobotlar | `/reports/` |
| Jamoa va takliflar | `/company/members/` |
| Bildirishnomalar | `/notifications/` |
| Obuna / tariflar | `/subscriptions/plans/` |
| Kompaniya profili va sozlamalari | `/company/`, `/company/settings/` |
| Barcha kompaniyalar (faqat Platform Admin) | `/platform/companies/` |
| Django admin | `/admin/` |

Interfeys **English / Русский / O'zbekcha** tillarida, yorug' va qorong'i rejimda ishlaydi.

## Texnologiyalar

Python · Django 6 · PostgreSQL · Redis (cache, Channels, Celery broker) · Celery + Celery Beat ·
Django Channels (WebSocket) · Uvicorn · Docker / Docker Compose · Django Templates + CSS/JS (frameworksiz).

## Loyiha tuzilmasi

```
teamflow/
├── config/
│   ├── settings/{base,development,production}.py
│   ├── urls.py · asgi.py · wsgi.py · celery.py
├── apps/
│   ├── accounts/        # User (email login), rollar, takliflar, profil, jamoa
│   ├── companies/       # Company (tenant), sozlamalar, platform ro'yxati
│   ├── projects/        # Project CRUD (tenant-scoped)
│   ├── tasks/           # Task + Comment, status, kalendar, deadline reminder
│   ├── notifications/   # Notification modeli, notify_user(), WebSocket consumer
│   ├── subscriptions/   # Free / Pro / Max, to'lov kartasi (mock billing) + seed migratsiya
│   ├── dashboard/       # Landing, dashboard, hisobot, qidiruv, Redis cache
│   └── common/          # Dekoratorlar (rol/tenant), kontekst, kalendar yordamchilari
├── templates/           # base.html, layouts/, partials/, 403/404/500
├── static/{css,js}/     # styles.css, app.js
├── locale/{uz,ru}/      # Tarjimalar
├── requirements/        # base, development, production, testing (UTF-8)
├── Dockerfile · docker-compose.yml · .env.example
└── manage.py
```

## Tez ishga tushirish

### 1) Docker bilan (tavsiya etiladi)

```bash
cp .env.example .env          # SECRET_KEY va boshqalarni o'zgartiring
docker compose up --build
docker compose exec web python manage.py createsuperuser   # Platform Admin
```

`web` (HTTP + WebSocket, :8000), `db` (PostgreSQL), `redis`, `celery_worker`, `celery_beat` ishga tushadi.
Migratsiyalar va `collectstatic` `web` startida avtomatik bajariladi. Sayt: http://localhost:8000

### 2) Docker'siz (lokal)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements/development.txt
cp .env.example .env     # DB_NAME va REDIS_URL ni bo'sh qoldirsangiz SQLite + xotira cache ishlatiladi
python manage.py migrate
python manage.py createsuperuser
uvicorn config.asgi:application --reload     # HTTP + WebSocket
```

`REDIS_URL` bo'sh bo'lsa, cache va channel layer xotirada ishlaydi, Celery vazifalari (taklif xati)
worker'siz shu zahoti bajariladi. To'liq rejim uchun Redis + `celery -A config worker` va
`celery -A config beat --scheduler django_celery_beat.schedulers:DatabaseScheduler` ishga tushiring.

## Rollar va ruxsatlar

| Amal | Employee | Manager | Platform Admin |
| --- | :-: | :-: | :-: |
| Loyiha/vazifalarni ko'rish (o'z kompaniyasi) | ✅ | ✅ | ✅ (hamma) |
| Loyiha va vazifa yaratish/tahrirlash/o'chirish | ❌ | ✅ | ✅ |
| O'ziga biriktirilgan vazifa statusini o'zgartirish | ✅ | ✅ | ✅ |
| Izoh qoldirish | ✅ | ✅ | ✅ |
| A'zo taklif qilish, rol o'zgartirish, faolsizlantirish | ❌ | ✅ | ✅ |
| Platform Admin rolini berish | ❌ | ❌ | ✅ |
| Tarifni o'zgartirish / kartani qo'shish | ❌ | ✅ | ❌ |
| Kompaniyani bloklash | ❌ | ❌ | ✅ |

## Multi-tenancy

- Har bir biznes yozuv (`User`, `Project`, `Task`, `Comment`, `Notification`) `Company` bilan bog'langan.
- `apps/common/decorators.py`: `company_member_required`, `manager_required`, `platform_admin_required`,
  `company_scoped_queryset`, `same_company_object` — har bir view'da qo'llanadi (defense-in-depth).
- Bloklangan kompaniya a'zolari tizimdan foydalana olmaydi (403).

## Testlar

```bash
python manage.py test
```

Qamrov: ro'yxatdan o'tish/kirish/chiqish, rol ruxsatlari, privilege-escalation himoyasi, tenant isolation,
loyiha/vazifa CRUD, tarif limitlari, bildirishnomalar, deadline reminder va barcha sahifalarning render bo'lishi.

## Muhim eslatmalar

- `.env`, `db.sqlite3`, `staticfiles/`, `myenv/`, `__pycache__/` Git'ga kiritilmaydi (`.gitignore`).
- Production'da `DJANGO_SETTINGS_MODULE=config.settings.production`, haqiqiy `SECRET_KEY`, HTTPS va
  statik fayllar uchun nginx/WhiteNoise tavsiya etiladi.
- To'lov tizimi hozircha mock (haqiqiy pul yechilmaydi).
