# License Admin + Flask API

نظام مستقل لإدارة مفاتيح الوصول لتطبيقك.

## التشغيل محليًا

Python 3.12+:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Android/Termux: source .venv/bin/activate
pip install -r requirements.txt
```

اضبط المتغيرات البيئية الموجودة في `.env.example`، ثم:

```bash
python app.py
```

افتح:

`http://127.0.0.1:5000/admin/login`

## PostgreSQL

ضع `DATABASE_URL` إلى رابط PostgreSQL الخاص بك، مثال عام:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

## API

### التحقق من مفتاح

```http
POST /api/login
Content-Type: application/json

{
  "key": "VIP-ABC123-DEF456-GHI789",
  "device_id": "android-device-id"
}
```

نجاح:

```json
{
  "ok": true,
  "valid": true,
  "token": "...",
  "expires_at": "..."
}
```

### إنشاء مفتاح عبر Admin API

يتطلب `X-Admin-Token`:

```http
POST /api/admin/keys
X-Admin-Token: YOUR_ADMIN_API_TOKEN
Content-Type: application/json

{"days":30}
```

## النشر على Railway/Render

- Build/Install: `pip install -r requirements.txt`
- Start: `gunicorn app:app`
- أضف:
  - `SECRET_KEY`
  - `ADMIN_USERNAME`
  - `ADMIN_PASSWORD`
  - `ADMIN_API_TOKEN`
  - `DATABASE_URL` (يفضل PostgreSQL في الإنتاج)

## ملاحظة أمنية

لا تضع `ADMIN_PASSWORD` أو `ADMIN_API_TOKEN` داخل تطبيق Android. هذه القيم يجب أن تبقى على الخادم.
المشروع مستقل ولا يفترض أو يستخرج API من أي APK آخر.
