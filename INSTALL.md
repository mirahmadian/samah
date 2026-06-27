# راهنمای نصب سامانه سماح روی سرور

این راهنما برای نصب روی یک سرور لینوکسی (Ubuntu 20.04+ یا Debian 11+) است.
سامانه طوری طراحی شده که فقط روی مسیرهای `/samah` و `/samahadmin` کار کند و
**با سایر سامانه‌های روی سرور شما تداخل نداشته باشد**.

---

## پیش‌نیازها

روی سرور این بسته‌ها باید نصب باشند:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git
```

---

## روش ۱: نصب خودکار (پیشنهادی)

```bash
# ۱. گرفتن کد روی سرور
git clone <آدرس-ریپازیتوری-شما> samah
cd samah
git checkout claude/samah-registration-system-s6lz48

# ۲. اجرای اسکریپت نصب خودکار
chmod +x deploy.sh
sudo bash deploy.sh
```

اسکریپت به‌صورت خودکار:
- محیط مجازی پایتون می‌سازد و وابستگی‌ها را نصب می‌کند
- یک کلید امنیتی (SECRET_KEY) تصادفی تولید می‌کند
- دیتابیس را می‌سازد و کاربر ادمین پیش‌فرض را ایجاد می‌کند
- سرویس systemd (به نام `samah`) را راه می‌اندازد تا با ریستارت سرور هم بالا بیاید
- کانفیگ nginx را روی پورت داخلی `8200` تنظیم می‌کند

> اگر پورت `8200` روی سرورتان اشغال است، با متغیر محیطی پورت دیگری بدهید:
> ```bash
> sudo SAMAH_PORT=8300 bash deploy.sh
> ```

پس از پایان، آدرس دسترسی در خروجی نمایش داده می‌شود:
- پنل ثبت‌نام: `http://آی‌پی‌سرور/samah/`
- پنل مدیریت: `http://آی‌پی‌سرور/samahadmin/`

---

## روش ۲: نصب دستی (برای کنترل کامل)

```bash
cd samah

# محیط مجازی
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# ساخت دیتابیس
python3 -c "from app import create_app; create_app()"

# اجرای آزمایشی
python3 app.py     # روی http://localhost:5000
```

برای محیط تولیدی به جای `python3 app.py` از gunicorn استفاده کنید:

```bash
gunicorn -c gunicorn.conf.py wsgi:application
```

---

## ورود به سامانه

| پنل | آدرس | اطلاعات ورود |
|------|------|--------------|
| مدیریت | `/samahadmin/` | کاربری: `admin` — رمز: `Admin@1234` |
| ثبت‌نام | `/samah/` | کد ملی معتبر + موبایل (مثلاً `09123456789`) |

> **مهم:** بلافاصله پس از اولین ورود، از منوی «کاربران ادمین» رمز عبور پیش‌فرض را تغییر دهید.

---

## دستورات مدیریت سرویس

```bash
sudo systemctl status samah      # وضعیت سرویس
sudo systemctl restart samah     # ری‌استارت
sudo systemctl stop samah        # توقف
sudo journalctl -u samah -f      # مشاهده لاگ زنده
```

---

## فعال‌سازی HTTPS (اختیاری ولی توصیه‌شده)

اگر دامنه دارید:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d samah.example.com
```

---

## نکات اتصال به سرویس‌های واقعی

این پیاده‌سازی برای موارد زیر **شبیه‌سازی (Mock)** دارد که هنگام بهره‌برداری واقعی باید جایگزین شوند:

1. **احراز هویت دولت من (SSO)** — در `samah_app/routes.py` تابع `login()`؛ باید به `https://sso.my.gov.ir/login` متصل شود.
2. **استعلام ثبت احوال** — تابع `mock_civil_registry()`؛ باید به وب‌سرویس ثبت احوال وصل شود.
3. **درگاه پرداخت بانکی** — مسیر `payment()`؛ باید به درگاه IPG بانک متصل شود.
4. **احراز شبا (بانک مرکزی)** — مسیر `cancel_member()`؛ برای تأیید شماره شبای منصرفین.

هر چهار نقطه با کامنت در کد مشخص شده‌اند تا اتصال آسان باشد.
