# دستیار آفلاین حسابداری ایران

یک هسته MVP ماژولار برای دریافت خروجی Excel/CSV نرم‌افزارهای حسابداری ایرانی، پاک‌سازی و کنترل قطعی داده‌ها، تحویل امن ابهام‌ها به هر هوش مصنوعی **بدون اتصال API** و تولید گزارش حرفه‌ای فارسی.

> این برنامه هیچ درخواست شبکه‌ای ارسال نمی‌کند. تصمیم AI تنها با فایل‌های قابل بازرسی وارد و خارج می‌شود؛ بنابراین کل فرایند تحت کنترل کاربر و قابل حسابرسی است.

## قابلیت‌ها

- خواندن Excel و CSV و تحمل نام‌های رایج فارسی/انگلیسی ستون‌ها
- یکسان‌سازی `ی/ي`، `ک/ك`، ارقام فارسی، عربی و انگلیسی
- تبدیل دوطرفه تاریخ شمسی/میلادی و نگهداری هر دو مقدار
- نگهداری مبالغ به‌صورت عدد واقعی، کنترل ماهیت بدهکار/بستانکار و تراز اسناد
- قواعد قطعی برای موارد روشن؛ عدم حدس در موارد مبهم
- بسته‌های prompt مستقل برای Claude، ChatGPT یا هر مدل دیگری
- اعتبارسنجی سخت‌گیرانه پاسخ با Pydantic و تولید خودکار پرامپت اصلاحی تا دو مرتبه
- ارجاع امن به بررسی انسانی در صورت شکست پاسخ، بدون توقف کل پردازش
- audit trail شامل داده ورودی، نام و SHA-256 پرامپت، خروجی خام، خروجی معتبر و زمان رخداد
- خروجی Excel راست‌به‌چپ با داشبورد، نمودار، کنترل اسناد، هشدارها، فیلتر، ردیف فریز، فرمت پولی و تنظیمات چاپ

## معماری

```text
project/
├── core/                     مدل‌های دامنه، تاریخ، متن و Schemaهای AI
├── parsers/                  قواعد قطعی و خواندن Excel/CSV
├── ai_bridge/
│   ├── prompts/              تمام پرامپت‌ها؛ هیچ پرامپتی در کد hardcode نشده
│   └── client.py             handoff آفلاین، validation، correction و audit
├── exporters/
│   ├── templates/default.json تنظیمات ظاهر قابل تغییر
│   └── excel_report.py       گزارش فارسی حرفه‌ای
├── ai_tasks/
│   ├── pending/              وظایف و پاسخ‌های در انتظار
│   ├── completed/            تصمیمات پذیرفته‌شده
│   └── rejected/             موارد ارجاعی به انسان
├── examples/sample_input.xlsx
├── tests/
└── run_example.py
```

## نصب سریع

نیازمندی: Python 3.11 یا جدیدتر.

```bash
cd project
python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_example.py
```

گزارش در `output/گزارش_حسابداری.xlsx` ایجاد می‌شود. در اولین اجرا، موارد مبهم در `ai_tasks/pending/` قرار می‌گیرند.

## گردش کار آفلاین AI

برای هر ابهام سه نام فایل مرتبط وجود دارد:

- `TX-....task.json`: متادیتای غیرقابل‌ابهام وظیفه
- `TX-....prompt.md`: پرامپت کامل و قابل‌ارسال به AI
- `TX-....response.json`: نام فایلی که پاسخ باید در آن ذخیره شود

### مراحل

1. فایل `*.prompt.md` را باز کنید و کل محتوای آن را به Claude یا ChatGPT بدهید.
2. AI موظف است فقط JSON مطابق Schema موجود در همان پرامپت بدهد.
3. JSON را بدون code fence در نام `*.response.json` خواسته‌شده و کنار prompt ذخیره کنید.
4. دوباره اجرا کنید:

```bash
python run_example.py
```

پاسخ معتبر اعمال و همه فایل‌های مربوط به آن به `ai_tasks/completed/` منتقل می‌شوند. پاسخ نامعتبر باعث تولید `*.correction-1.md` و سپس `*.correction-2.md` می‌شود. بعد از دو تلاش اصلاحی ناموفق، تراکنش «نیازمند بررسی انسانی» می‌شود و pipeline ادامه می‌یابد.

### نمونه پاسخ

مقادیر باید با task و فهرست حساب‌های همان prompt منطبق باشند:

```json
{
  "task_id": "TX-شناسه-واقعی",
  "normalized_description": "واریز بابت تسویه حساب مشتری",
  "transaction_type": "دریافت",
  "suggested_account_code": "110101",
  "suggested_account_name": "بانک‌ها",
  "confidence": 0.82,
  "reasoning": "وجود عبارت واریز و قرینه تسویه، دریافت بانکی را نشان می‌دهد.",
  "requires_human_review": false
}
```

سیستم علاوه بر Schema، مجاز بودن کد حساب و یکسان بودن `task_id` را نیز کنترل می‌کند. نام حساب دریافتی مبنای ثبت نیست و نام معتبر از کدینگ داخلی خوانده می‌شود.

## اجرای فایل واقعی

```bash
python run_example.py /path/to/ledger.xlsx --output output/company_report.xlsx
python run_example.py /path/to/ledger.csv  --output output/company_report.xlsx
```

ستون‌های قابل‌شناسایی شامل این نام‌هاست:

| داده | نمونه نام ستون |
|---|---|
| شماره سند | شماره سند، سند، `document_number`، `doc_no` |
| تاریخ | تاریخ، تاریخ سند، `date` |
| شرح | شرح، شرح سند، `description`، `memo` |
| مبلغ | بدهکار/بستانکار، مبلغ بدهکار/بستانکار، `debit`/`credit` |
| حساب | کد حساب/نام حساب، `account_code`/`account_name` |

یک ردیف خراب متوقف‌کننده نیست: در شیت «ردیف‌های نامعتبر» ثبت می‌شود و بقیه فایل پردازش خواهد شد.

## ساخت مجدد فایل نمونه و اجرای تست

```bash
python examples/create_sample.py
pytest -q
```

## حریم خصوصی و حسابرسی

- برنامه از کتابخانه یا سرویس آنلاین AI استفاده نمی‌کند.
- پیش از ارسال prompt به یک سرویس خارجی، مسئول حفاظت و ناشناس‌سازی اطلاعات محرمانه شرکت کاربر است.
- رخدادها در `logs/ai_audit.jsonl` ثبت می‌شوند. فایل audit ممکن است داده حساس داشته باشد و نباید عمومی شود.
- گزارش خروجی ابزار کمکی است و جایگزین تأیید حسابدار مسئول یا الزامات قانونی و مالیاتی ایران نیست.

## توسعه آینده

مرزهای ماژول‌ها برای افزودن کدینگ اختصاصی هر شرکت، parserهای سپیدار/هلو/راهکاران، تطبیق بانکی، ارزش افزوده، سامانه مودیان، حقوق و دستمزد و adapter مستقل ERPNext آماده شده‌اند. فایل‌های prompt و theme بدون تغییر کد قابل نسخه‌بندی هستند.

---

# English Quickstart

This is an offline-first Iranian accounting normalization and review pipeline. It parses Excel/CSV ledgers, applies deterministic rules, exports unresolved decisions as self-contained prompt files, validates returned JSON, and creates a polished RTL Excel report. It performs **no AI network calls**.

```bash
cd project
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_example.py
pytest -q
```

For every unresolved transaction, send `ai_tasks/pending/*.prompt.md` to the AI provider of your choice. Save its raw JSON as the requested `.response.json` file and rerun the same command. Invalid answers produce up to two correction prompts; persistent failures are safely marked for human review instead of corrupting the ledger or stopping the run.
