# PDPA Blur

เอกสารฉบับนี้อธิบายภาพรวม แนวคิดสถาปัตยกรรม ขั้นตอนติดตั้งและการใช้งานของโปรเจกต์ PDPA Blur ตั้งแต่ต้นจนจบ เพื่อให้กลับมาอ่านทบทวนหรือสานต่อได้ง่ายในอนาคต

---

## 1. ภาพรวม (Project Overview)

PDPA Blur เป็นระบบ full-stack สำหรับช่วยคอนเทนต์ครีเอเตอร์ทำวิดีโอให้สอดคล้องกับ PDPA (กฎหมายคุ้มครองข้อมูลส่วนบุคคล) โดยมีคุณสมบัติหลัก:

- **Face Whitelisting**: ระบุ “ใบหน้าหลัก” ผ่านภาพอ้างอิง ระบบจะเบลอเฉพาะคนอื่น ส่วนเจ้าของจะยังชัดอยู่
- **โหมดการประมวลผล 2 แบบ**
  - `detailed` ตรวจทุกเฟรมเพื่อความแม่นยำสูงสุด
  - `fast` ตรวจทุก 2 เฟรมเพื่อความเร็ว พร้อมกติกาที่เข้มงวดขึ้นในการจำแนกใบหน้า
- **คิวงานแบบ background**: งานเบลอวิดีโอรันบน thread แยก มี job store เก็บสถานะ/ความคืบหน้า
- **Frontend UI** (Nuxt 3): หน้าเดียวที่ครอบ workflow ทั้งหมด ตั้งแต่เลือกรูป reference ปรับ blur level ไปจนถึงดาวน์โหลดผลลัพธ์

---

## 2. สถาปัตยกรรม (Architecture)

```
┌─────────────┐        ┌──────────────────────────┐
│   Nuxt 3    │  REST  │        FastAPI           │
│  Frontend   │◀──────▶│ - Upload faces/videos    │
│  (pages/)   │        │ - Job queue in-memory    │
└─────┬───────┘        │ - Video blur service     │
      │                └──────────┬──────────────┘
      │                           │
      │         ┌─────────────────┴────────────────┐
      │         │OpenCV + face_recognition pipeline │
      │         │   • Mediapipe face detection      │
      │         │   • Face embeddings & matching    │
      │         │   • Gaussian blur per blur level  │
      │         │   • FFmpeg remux audio            │
      │         └───────────────────────────────────┘
      │
      ▼
 media/ storage (reference faces, uploads, processed)
```

---

## 3. โครงสร้างโปรเจกต์ (Repository Layout)

```
pdpa-blur/
├─ README.md                # เอกสารฉบับนี้
├─ backend/
│  ├─ app/
│  │  ├─ main.py            # จุดเริ่ม FastAPI + logging
│  │  ├─ core/              # config (Pydantic Settings), job store in-memory
│  │  ├─ api/               # เส้นทาง REST (faces, videos, jobs, meta)
│  │  ├─ services/          # face_service + video_service (งานหนักทั้งหมด)
│  │  ├─ schemas/           # Pydantic models ที่ใช้ validate input/output
│  │  ├─ utils/             # helper จัดการไฟล์ + schedule cleanup
│  │  ├─ face.py / face_utils.py # face registry และ utility
│  │  └─ workers/           # โครงสำหรับขยาย background worker ในอนาคต
│  ├─ media/                # สร้างเมื่อรัน เก็บ uploads/reference/processed
│  ├─ requirements.txt
│  ├─ pyproject.toml
│  └─ .env.example
└─ frontend/
   ├─ app.vue, pages/, layouts/
   ├─ composables/useApi.ts
   ├─ stores/useProcessingStore.ts
   ├─ package.json, tsconfig.json, tailwind.config.ts
   └─ .env.example
```

---

## 4. Prerequisites

| เครื่องมือ | เวอร์ชันที่แนะนำ | หมายเหตุ |
|-------------|------------------|----------|
| Python      | ≥ 3.9            | ใช้ virtualenv จัดการ environment |
| Node.js     | ≥ 18             | ใช้ npm หรือ pnpm/yarn ได้ |
| FFmpeg      | ล่าสุด           | จำเป็นสำหรับ remux audio จากวิดีโอต้นฉบับ |
| CMake       | ≥ 3.22           | face_recognition/dlib ต้องใช้ตอน build |
| Git         | -                | สำหรับจัดการเวอร์ชันโปรเจกต์ |

**หน้าที่ของเครื่องมือหลัก**
- **Python** – รันฝั่ง backend และสคริปต์จัดการระบบต่าง ๆ
- **Node.js** – สร้างและรัน Nuxt frontend ในโหมด dev/prod
- **FFmpeg** – ผนวกเสียงกลับไปยังวิดีโอที่เบลอเสร็จแล้ว (video_service เรียกผ่าน subprocess)
- **CMake / build-essential** – ใช้คอมไพล์โมดูล dlib ที่อยู่เบื้องหลัง `face_recognition`
- **Git** – เก็บเวอร์ชันซอร์สโค้ดและทำงานร่วมกับทีม

macOS: `brew install ffmpeg cmake`

Ubuntu: `sudo apt install ffmpeg cmake build-essential`

Windows: ใช้ [FFmpeg binaries](https://ffmpeg.org/download.html) + `choco install cmake`

### 4.1 ขั้นตอนเตรียมโปรเจกต์ครั้งแรก

```bash
# 1) ดาวน์โหลดซอร์สโค้ด
git clone https://github.com/YOUR_ORG/pdpa-blur.git
cd pdpa-blur

# 2) ตรวจสอบเวอร์ชันเครื่องมือพื้นฐาน
python3 --version
node --version
ffmpeg -version

# 3) ติดตั้งตัวจัดการแพ็กเกจตามระบบปฏิบัติการ (ถ้ายังไม่มี)
#   - macOS: brew install ffmpeg cmake
#   - Ubuntu: sudo apt update && sudo apt install -y ffmpeg cmake build-essential python3-venv
#   - Windows (PowerShell): choco install ffmpeg cmake python -y
```

> **หมายเหตุ:** repository นี้รวมทั้ง backend และ frontend อยู่ด้วยกัน คำสั่งที่จะอธิบายต่อจากนี้จะแยกเป็นสองส่วนหลัก

---

## 5. การตั้งค่า Backend

1. **สร้าง virtualenv และติดตั้งไลบรารี**
   ```bash
   cd pdpa-blur/backend
   python3 -m venv .venv
   source .venv/bin/activate          # Windows ใช้ .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **ตั้งค่า environment variables**
   - คัดลอก `.env.example` → `.env`
   - ตัวแปรที่ควรทราบ:
     - `api_prefix=/api`
     - `allow_insecure_cors=true`
     - `redis_url=redis://localhost:6379/0` (ใช้เป็น placeholder)
     - `media_root=./media`
     - `LOG_LEVEL=INFO` (ตั้ง `DEBUG` เมื่ออยากเห็น log ละเอียด โดยเฉพาะจาก `video_service`)

3. **รันเซิร์ฟเวอร์พัฒนา**
   ```bash
   LOG_LEVEL=DEBUG uvicorn app.main:app --reload --port 8000
   ```
   - จะสร้างโฟลเดอร์ `media/reference_faces`, `media/uploads`, `media/processed`
   - job store เป็น in-memory หากรีสตาร์ตข้อมูลจะหาย ควรดาวน์โหลดผลลัพธ์ก่อน

4. **REST Endpoints สำคัญ**
   - `POST /api/faces/reference` – อัปโหลดรูป reference (หลายรูปได้)
   - `POST /api/videos/blur` – สร้างงานเบลอ (ต้องส่ง `user_id`, `mode`, `blur_level`, `video`)
   - `GET /api/jobs/{job_id}` – เช็กสถานะ/ความคืบหน้า (download URL จะถูกเติมเมื่อเสร็จ)
   - `GET /api/videos/{job_id}/download` – ดาวน์โหลดไฟล์ผลลัพธ์
   - `GET /api/meta/ping` – ตรวจสุขภาพระบบเบื้องต้น

### 5.1 Python dependencies และหน้าที่

| แพ็กเกจ | คำสั่งติดตั้ง | บทบาท |
|----------|----------------|--------|
| `fastapi` | `pip install fastapi` | Web framework สำหรับสร้าง REST API |
| `uvicorn[standard]` | `pip install "uvicorn[standard]"` | ASGI server ใช้รัน FastAPI (รวมตัวเร่งความเร็ว) |
| `python-multipart` | `pip install python-multipart` | รองรับ `multipart/form-data` สำหรับอัปโหลดรูป/วิดีโอ |
| `pydantic` | `pip install pydantic>=2.11` | ใช้ประกาศ schema และ validate request/response |
| `pydantic-settings` | `pip install pydantic-settings` | จัดการคอนฟิกผ่าน `.env` แบบ type-safe |
| `numpy` | `pip install numpy` | โครงสร้าง array/เวกเตอร์สำหรับงานภาพและคณิตศาสตร์ |
| `opencv-contrib-python` | `pip install opencv-contrib-python==4.8.1.78` | ใช้เปิดวิดีโอ, ทำ Gaussian blur, utility ด้านภาพ |
| `mediapipe` | `pip install mediapipe==0.10.14` | Face Detection (Google) ช่วยหา bounding box ที่แม่นกว่ารุ่น HOG |
| `face-recognition` | `pip install face-recognition` | แปลงใบหน้าเป็น embedding 128 มิติและคำนวณระยะ |
| `face-recognition-models` | `pip install face-recognition-models` | โมเดล pre-trained (dlib) ที่ `face-recognition` เรียกใช้ |

> การรัน `pip install -r requirements.txt` จะติดตั้งแพ็กเกจทั้งหมดด้านบน (ยกเว้น `mediapipe` ซึ่งควรติดตั้งเพิ่มตามคำสั่งที่ระบุ)

---

## 6. การตั้งค่า Frontend

1. **ติดตั้ง dependencies**
   ```bash
   cd pdpa-blur/frontend
   npm install
   ```

2. **ตั้งค่า API Base**
   ```bash
   cp .env.example .env
   # ปรับค่า NUXT_PUBLIC_API_BASE หาก backend อยู่คนละ host/port
   ```

3. **รันโหมดพัฒนา**
   ```bash
   npm run dev
   ```
   - เปิดที่ `http://localhost:3000`
   - หากต้องการ build production: `npm run build` และ `npm run preview`

### 6.1 npm dependencies และหน้าที่

| แพ็กเกจ | คำสั่งติดตั้ง (ถ้าต้องเพิ่มเอง) | บทบาท |
|----------|-----------------------------------|--------|
| `nuxt` | `npm install nuxt` | Framework หลัก (Vue 3 + Vite) ใช้สร้าง SPA/SSR |
| `@pinia/nuxt` + `pinia` | `npm install @pinia/nuxt pinia` | State management สำหรับจัดการสถานะงานประมวลผล |
| `@nuxtjs/tailwindcss` | `npm install @nuxtjs/tailwindcss` | เสริม TailwindCSS ให้ทำงานกับ Nuxt ได้ทันที |
| `@vueuse/nuxt` | `npm install @vueuse/nuxt` | Utilities (composables) เพิ่มเติมสำหรับ Vue 3 |
| `ofetch` | `npm install ofetch` | wrapper fetch ที่ Nuxt ใช้ภายใน (ทำให้ SSR-friendly) |
| `axios` | `npm install axios` | ใช้ในบางส่วนที่ต้องการ HTTP client ลักษณะ promise-based |

**Dev dependencies ที่แนะนำ**

| แพ็กเกจ | บทบาท |
|----------|--------|
| `eslint`, `eslint-plugin-vue`, `@typescript-eslint/*` | ตรวจมาตรฐานโค้ด Vue + TypeScript |
| `prettier`, `eslint-config-prettier` | จัดรูปแบบโค้ดอัตโนมัติให้เข้ากับ ESLint |
| `typescript`, `@types/node`, `vue-eslint-parser`, `globals` | รองรับการพัฒนาแบบ TypeScript บน Nuxt |

> ปกติ `npm install` จะติดตั้งทั้ง dependencies และ devDependencies ตาม `package.json` อยู่แล้ว ตารางนี้ไว้ใช้อ้างอิงว่าทำไมเราจำเป็นต้องใช้แต่ละแพ็กเกจ

---

## 7. ขั้นตอนใช้งาน (Typical Workflow)

### ฝั่งผู้ใช้ (ผ่าน UI)
1. อัปโหลดภาพอ้างอิงใบหน้าตัวเอง (หลายรูปเพิ่มความแม่นยำ)
2. เลือกโหมด `fast` หรือ `detailed` + เลือกระดับเบลอ 1–10
3. อัปโหลดวิดีโอ → ระบบจะแสดง progress
4. เมื่อเสร็จจะมีปุ่มดาวน์โหลดวิดีโอผลลัพธ์

### ฝั่งผู้พัฒนา/ผู้ดูแล
1. เปิด `LOG_LEVEL=DEBUG` เมื่อทดสอบ เพื่อดู log `face dist`, `ref_ok`, `run_ok`
2. ไฟล์ผลลัพธ์อยู่ใน `backend/media/processed/` (ระบบตั้งเวลา auto-delete ตามที่สั่งใน `schedule_file_expiration`)
3. หากต้องการเก็บไฟล์นานขึ้นให้ปรับเวลาที่เรียก `schedule_file_expiration`

---

## 8. เบื้องลึกฝั่ง Backend

### การสร้าง Face Embedding
- ใช้ Mediapipe Face Detection หา bounding box
- ส่งภาพครอปเข้า `face_recognition.face_encodings` → ได้ 128-D embedding
- เก็บไว้ใน `face_registry` พร้อมตั้งเวลาหมดอายุ (ดีฟอลต์ 300 วินาที)

### การประมวลผลวิดีโอ
- `_blur_video_frames` เปิดวิดีโอด้วย OpenCV และเขียนผลลัพธ์ออกเป็นไฟล์ชั่วคราว
- `_detect_and_update` ใช้ Mediapipe + face_recognition เพื่อตรวจจับและแยกผู้ใช้กับบุคคลอื่น มี hysteresis (`user_hits/user_misses`) + running embedding สำหรับลดการกระพริบ
- โหมด `fast` บังคับ `require_reference_match=True` และมีเงื่อนไขระยะเข้มกว่าก่อนจะอนุญาตให้เป็นผู้ใช้
- เมื่อจบงานเรียก `_mux_audio_with_ffmpeg` เพื่อผนวกเสียงจากวิดีโอต้นฉบับกลับเข้ามา

### การจัดการไฟล์และงาน
- `utils/files.py::save_upload_file` รับผิดชอบการบันทึกไฟล์อัปโหลด
- `utils/cleanup.py` มี `schedule_file_expiration` และ `schedule_profile_expiration` ช่วยลบไฟล์/โปรไฟล์อ้างอิงภายหลัง
- `core/jobs.py` ดูแล job store (thread-safe dictionary) สำหรับเก็บสถานะงานและผลลัพธ์

---

## 9. โครงสร้างและโมดูลฝั่ง Frontend

| ไฟล์/ไดเรกทอรี | หน้าที่ |
|-----------------|---------|
| `pages/index.vue` | UI หลักทั้งหมด: อัปโหลด reference, ส่งงาน, polling สถานะ, ดาวน์โหลด |
| `composables/useApi.ts` | wrapper fetch ที่อ่าน `NUXT_PUBLIC_API_BASE` จาก runtime config |
| `stores/useProcessingStore.ts` | Pinia store เก็บสถานะงานปัจจุบัน (progress, download URL) |
| `components/*` | ส่วน UI ประกอบ เช่น Preview blur, การ์ดไฟล์ |
| `layouts/default.vue` | ลักษณะหน้าหลักส่วน header/footer |
| `tailwind.config.ts` / `postcss.config.js` | ตั้งค่าธีม Tailwind |

---

## 10. Logging & Debugging

- ตั้ง `LOG_LEVEL=DEBUG` เพื่อดู log ละเอียดจาก backend
- `video_service` จะพิมพ์ `face dist`, `ref_ok`, `run_ok`, `hits`, `misses` ใช้วิเคราะห์ว่าโหมดเร็ว/ละเอียดทำงานถูกต้องหรือไม่
- หาก FFmpeg ล้มเหลวจะถูก raise เป็น `RuntimeError` พร้อม stderr ที่อ่านได้จาก log

---

## 11. Storage & Cleanup

- media ทั้งหมดถูกเก็บใน `backend/media/`
  - `reference_faces/` – รูปอ้างอิงผู้ใช้
  - `uploads/` – วิดีโอต้นฉบับจากผู้ใช้
  - `processed/` – วิดีโอผลลัพธ์ (ลบภายใน ~5 นาทีตาม scheduler)
- โฟลเดอร์ `__pycache__` เป็น cache ของ Python ไม่จำเป็นต้องลบทิ้งเป็นระยะ (ลบแล้ว Python ก็สร้างใหม่อยู่ดี)

---

## 12. ขั้นตอนแนะนำก่อนส่งมอบ/ใช้งานจริง

1. รัน smoke test ด้วยวิดีโอตัวอย่าง ทั้งโหมด `fast` และ `detailed`
2. ตรวจ log backend ว่าไม่มี error จาก FFmpeg หรือ face_recognition
3. commit/tag และจัดทำ release note หากจะเผยแพร่
4. หากจะ deploy production ให้เตรียม Reverse Proxy + SSL และพิจารณาเปลี่ยน job store เป็น Redis/คิวจริง

---

## 13. แนวทางพัฒนาต่อ (Ideas)

- ย้าย job queue ไป Celery/RQ เพื่อกระจายงานได้หลายเครื่อง
- เก็บ embeddings/metadata ในฐานข้อมูลถาวร (PostgreSQL หรือ Redis)
- เพิ่มระบบ white-list หลายใบหน้า และ UI เลือกคนที่ต้องการคงภาพชัด
- เพิ่มระบบแจ้งเตือนเมื่อประมวลผลเสร็จ (เช่น ส่งอีเมล หรือใช้ WebSocket)
- เพิ่ม automated tests (unit/integration) และ pipeline CI/CD

---

## 14. Troubleshooting

| อาการ | วิธีแก้ |
|--------|--------|
| `face_recognition` install ไม่ผ่าน | ตรวจว่าเครื่องมี CMake และ library สำหรับ build dlib (macOS: `brew install cmake pkg-config`) |
| โหมดเร็วเบลอผิดคน | เปิด DEBUG แล้วดูค่าจาก log เพื่อจูน `match_threshold`/`min_confidence_gap` เพิ่มเติม |
| วิดีโอผลลัพธ์ไม่มีเสียง | ตรวจว่ามี FFmpeg อยู่ใน PATH และไฟล์ต้นฉบับมี track เสียงจริง |
| ดาวน์โหลดไม่ได้ (404) | งานอาจหมดอายุและไฟล์ถูกลบจาก scheduler ปรับเวลาที่ `schedule_file_expiration` หากอยากเก็บนานขึ้น |

---

## 15. สรุป

โปรเจกต์ PDPA Blur อยู่ในสภาพพร้อมใช้งานสำหรับงาน Dev/PoC: โครงสร้างชัดเจน, UI ใช้งานง่าย, และ logic การเบลอที่ปรับจูนแล้วทั้งโหมดเร็วและโหมดละเอียด หากต้องการยกระดับไป production ให้โฟกัสที่การเปลี่ยน job store, จัดการ storage ระยะยาว, เสริมระบบ auth และ automation การทดสอบ/ดีพลอย

> เก็บ README นี้ไว้เป็นคู่มือหลัก เมื่อกลับมาในอนาคตจะเข้าใจโครงสร้าง ระบบงาน และขั้นตอนตั้งค่าทั้งหมดได้ทันที
