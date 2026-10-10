# line-expense-bot

LINE bot สำหรับบันทึกรายรับ–รายจ่ายส่วนตัว พิมพ์ในแชทแล้วบอทจดลงฐานข้อมูลให้
พร้อมสรุปยอดแบบต่าง ๆ แยกตามหมวดหมู่ — ทำไว้ใช้เองแบบ mini ไม่ต้องมีเว็บแอป

## หลักการทำงาน

```
LINE chat ──► LINE Messaging API (webhook) ──► FastAPI (parse + บันทึก) ──► Turso (libSQL)
                                                     │
                                                     └─► reply กลับในแชท + Quick Reply
```

- **Rule-based parser** ไม่ใช้ LLM → ฟรี เร็ว และแม่นเมื่อใช้คนเดียว
- **Quick Reply ปุ่ม** ช่วยแก้หมวด/ลบรายการล่าสุดได้โดยไม่ต้องพิมพ์เยอะ
- **Turso** เก็บข้อมูลถาวร (ไฟล์ SQLite บน host ฟรีมักหายเมื่อ deploy ใหม่)

## วิธีใช้ (พิมพ์ในแชท)

| สิ่งที่พิมพ์ | ผลลัพธ์ |
|---|---|
| `50 กาแฟ` | บันทึกรายจ่าย 50 บาท หมวด "อาหาร" |
| `กาแฟ 50` | เหมือนด้านบน (สลับตำแหน่งได้) |
| `1,250 ค่าไฟ` | บันทึก 1,250 บาท หมวด "บิล" |
| `+25000 เงินเดือน` | บันทึกรายรับ 25,000 บาท |
| `สรุป` | สรุปของวันนี้ |
| `สรุปสัปดาห์` | สรุปสัปดาห์นี้ (จ.–อา.) |
| `สรุปเดือน` | สรุปเดือนนี้ + แยกหมวดเป็นบาร์ |
| `หมวด` | ดูหมวดทั้งหมด |
| `ลบล่าสุด` | ลบรายการล่าสุด |
| `แก้ อาหาร` | เปลี่ยนหมวดของรายการล่าสุด |
| `ช่วย` | วิธีใช้ |

## โครงสร้างโปรเจกต์

```
app/
  main.py         # FastAPI + webhook endpoint + logic ตอบข้อความ
  config.py       # โหลด env (LINE, Turso, timezone)
  db.py           # engine + session + model Transaction
  parser.py       # แปลงข้อความ → รายการ / คำสั่ง
  categories.py   # นิยามหมวด + keyword matching
  summary.py      # สร้างข้อความสรุป/ยืนยัน
  line_client.py  # helper ตอบกลับ LINE + Quick Reply
tests/
  test_parser.py
  test_summary.py
data/             # sqlite ตอน dev (ไม่ commit)
```

## เริ่มใช้งานในเครื่อง

```bash
cd line-expense-bot
uv venv --python 3.13 .venv
uv pip install --python .venv -r requirements-dev.txt
cp .env.example .env          # แล้วเติมค่าด้านล่าง
.venv/bin/uvicorn app.main:app --reload --port 8000
```

> ถ้ายังไม่ตั้ง Turso ให้ปล่อย `TURSO_DATABASE_URL` ว่างไว้ แอปจะใช้ไฟล์ `data/expense.db` ในเครื่องแทน

### 1) สร้าง LINE Messaging API channel
1. ไปที่ https://developers.line.biz/console/ สร้าง Provider + channel ชนิด **Messaging API**
2. คัดลอกจากหน้า console:
   - **Channel secret** → `LINE_CHANNEL_SECRET`
   - **Channel access token (long-lived)** → `LINE_CHANNEL_ACCESS_TOKEN`
3. เปิดใช้ "Use webhook" และปิด auto-reply/greeting ของ OA

### 2) ตั้ง Turso
```bash
# ติดตั้ง CLI (macOS)
brew install tursodatabase/tap/turso

turso auth login
turso db create line-expense-bot
turso db show line-expense-bot --url          # → TURSO_DATABASE_URL
turso db tokens create line-expense-bot       # → TURSO_AUTH_TOKEN
```

### 3) เปิด webhook ด้วย ngrok
```bash
ngrok http 8000
# นำ URL https://xxxx.ngrok-free.app ไปใส่ Webhook URL = https://xxxx.ngrok-free.app/callback
```
ตั้ง Webhook URL ที่ LINE console → Messaging API → Webhook URL แล้วกด **Verify**

## รันเทส

```bash
.venv/bin/python -m pytest -q
```

## Deploy ฟรีบน Render (แนะนำ)

โปรเจกต์มี `render.yaml` (Blueprint) + `Procfile` + `.python-version` เตรียมไว้แล้ว

### ขั้นตอน
1. push โปรเจกต์ขึ้น GitHub (repo ใหม่)
   ```bash
   cd line-expense-bot
   git init && git add . && git commit -m "line-expense-bot"
   git remote add origin <repo-url> && git push -u origin main
   ```
   > `.env` ถูก gitignore ไว้แล้ว ไม่มี secret หลุดขึ้น repo

2. Render → **New +** → **Blueprint** → เลือก repo → Render อ่าน `render.yaml` เอง
   - ถ้าไม่ใช้ Blueprint: **New +** → **Web Service** แล้วตั้ง
     - Build: `pip install -r requirements.txt`
     - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
     - Health check path: `/healthz`

3. ใส่ **Environment Variables** (ค่าลับ ใส่ใน dashboard):
   `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`
   (`APP_TIMEZONE` ตั้งให้แล้วใน `render.yaml` = `Asia/Bangkok`)

4. รอ deploy เสร็จ → ได้ URL เช่น `https://line-expense-bot.onrender.com`
   ทดสอบ: เปิด `https://line-expense-bot.onrender.com/healthz` ต้องได้ `{"status":"ok"}`

5. อัปเดต Webhook URL ใน LINE console → `https://line-expense-bot.onrender.com/callback` แล้วกด **Verify**

### กัน Render free sleep (สำคัญกับ LINE)
Render free จะ sleep หลัง idle 15 นาที ทำให้ข้อความแรกช้า ~1 นาที ตั้งตัวปลุกฟรี:
- **UptimeRobot** (ฟรี) → monitor ชนิด HTTP(s) ยิง `https://line-expense-bot.onrender.com/healthz` ทุก 5 นาที
- หรือ **cron-job.org** ยิงทุก 10–14 นาที
- โควตาฟรี 750 ชม./เดือน ≈ 31 วัน พอดีกับ 1 service รัน 24/7

> ทางเลือกอื่น: Koyeb (ตื่น 1–5 วิ แต่ต้องใส่บัตร), Oracle Always Free VM (always-on, ต้องมีบัตร)

### หมายเหตุ
- reply token ใช้ได้ครั้งเดียวและหมดอายุเร็ว บอทจึงตอบครั้งเดียวต่อข้อความ
- ถ้า LINE ส่ง event ซ้ำ จะถูกประมวลผลซ้ำ (ยังไม่กัน duplicate) — เพิ่มได้ทีหลังถ้าจำเป็น
- หลัง deploy แล้วไม่ต้องใช้ ngrok อีก (URL ถาวรแล้ว)
