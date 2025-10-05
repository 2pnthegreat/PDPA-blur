<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useApi } from '~/composables/useApi'
import { useProcessingStore } from '~/stores/useProcessingStore'
import type { JobState } from '~/stores/useProcessingStore'

interface FaceRegistrationResponse {
  user_id: string
  image_paths: string[]
  count: number
}

interface JobCreatedResponse {
  job_id: string
  state: JobState
}

interface JobStatusResponse {
  job_id: string
  state: JobState
  progress: number
  message?: string
  download_url?: string
}

type ProcessingMode = 'fast' | 'detailed'

interface ReferenceItem {
  id: string
  file: File
  previewUrl: string
}

const selectedBlur = ref(5)
const mode = ref<ProcessingMode>('fast')
const referenceFaces = ref<ReferenceItem[]>([])
const targetVideo = ref<File | null>(null)
const previewLevel = computed(() => selectedBlur.value * 10)
const previewBlurPx = computed(() => Math.round(selectedBlur.value * 2.2 + 1))
const previewImageSrc = computed(() => {
  if (referenceFaces.value.length) return referenceFaces.value[0].previewUrl
  return '/demo-cat.jpg'
})
const processingStore = useProcessingStore()
const isProcessing = ref(false)
const statusMessage = ref('')
const errorMessage = ref('')
const jobStatus = computed(() => processingStore.currentJob)
const displayProgress = computed(() => {
  const value = jobStatus.value?.progress
  if (typeof value !== 'number' || Number.isNaN(value) || !Number.isFinite(value)) {
    return 0
  }
  return Math.max(0, Math.min(100, Math.round(value)))
})
const userId = 'demo-user'

let pollHandle: ReturnType<typeof setInterval> | null = null

const formatBytes = (bytes: number) => {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, exponent)
  const fixed = value >= 10 || exponent === 0 ? value.toFixed(0) : value.toFixed(1)
  return `${fixed} ${units[exponent]}`
}

const createReferenceItem = (file: File): ReferenceItem => {
  const uid =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return {
    id: uid,
    file,
    previewUrl: URL.createObjectURL(file)
  }
}

const uploadReference = (files: FileList | null) => {
  if (!files?.length) return
  const newItems = Array.from(files).map(createReferenceItem)
  referenceFaces.value = [...referenceFaces.value, ...newItems]
}

const removeReference = (id: string) => {
  const index = referenceFaces.value.findIndex((item) => item.id === id)
  if (index === -1) return
  const [removed] = referenceFaces.value.splice(index, 1)
  URL.revokeObjectURL(removed.previewUrl)
}

const selectVideo = (files: FileList | null) => {
  if (!files?.length) return
  if (files.length > 1) {
    window.alert('เลือกได้ทีละไฟล์ ระบบจะใช้ไฟล์แรกเท่านั้น')
  }
  targetVideo.value = files[0]
}

const clearVideo = () => {
  targetVideo.value = null
}

const resetPoller = () => {
  if (pollHandle) {
    clearInterval(pollHandle)
    pollHandle = null
  }
}

const extractErrorMessage = (error: unknown) => {
  if (!error) return 'เกิดข้อผิดพลาดไม่ทราบสาเหตุ'
  if (typeof error === 'string') return error
  if (error instanceof Error && error.message) return error.message

  type ErrorPayload = {
    data?: { detail?: unknown }
    message?: string
    statusMessage?: string
  }

  const maybe = error as ErrorPayload
  const detail = maybe?.data?.detail
  if (detail) {
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const firstDetail = detail[0]
      if (typeof firstDetail === 'string') return firstDetail
      if (
        typeof firstDetail === 'object' &&
        firstDetail !== null &&
        'msg' in firstDetail &&
        typeof (firstDetail as Record<string, unknown>).msg === 'string'
      ) {
        return (firstDetail as Record<string, unknown>).msg as string
      }
    }
  }

  return maybe?.message || maybe?.statusMessage || 'เกิดข้อผิดพลาดไม่ทราบสาเหตุ'
}

const uploadReferenceFaces = async () => {
  const formData = new FormData()
  referenceFaces.value.forEach((item) => {
    formData.append('images', item.file)
  })
  formData.append('user_id', userId)
  return await useApi<FaceRegistrationResponse>({
    path: '/faces/reference',
    method: 'POST',
    body: formData
  })
}

const submitBlurJob = async () => {
  const formData = new FormData()
  formData.append('user_id', userId)
  formData.append('mode', mode.value)
  formData.append('blur_level', String(selectedBlur.value))
  if (targetVideo.value) {
    formData.append('video', targetVideo.value)
  }
  return await useApi<JobCreatedResponse>({
    path: '/videos/blur',
    method: 'POST',
    body: formData
  })
}

const pollJob = (jobId: string) =>
  new Promise<void>((resolve, reject) => {
    const fetchStatus = async () => {
      try {
        const status = await useApi<JobStatusResponse>({ path: `/jobs/${jobId}` })
        processingStore.updateJob({
          state: status.state,
          progress: status.progress,
          message: status.message,
          downloadUrl: status.download_url
        })

        if (status.state === 'completed') {
          statusMessage.value = 'ประมวลผลเสร็จแล้ว! ดาวน์โหลดวิดีโอที่เบลอแล้วได้เลย'
          resetPoller()
          resolve()
        } else if (status.state === 'failed') {
          errorMessage.value = status.message || 'เกิดข้อผิดพลาดระหว่างประมวลผล'
          resetPoller()
          reject(new Error(errorMessage.value))
        }
      } catch (error) {
        resetPoller()
        const message = extractErrorMessage(error)
        errorMessage.value = message
        reject(new Error(message))
      }
    }

    fetchStatus()
    resetPoller()
    pollHandle = setInterval(fetchStatus, 1500)
  })

const startProcessing = async () => {
  if (!referenceFaces.value.length || !targetVideo.value) {
    window.alert('กรุณาอัปโหลดรูปอ้างอิงอย่างน้อย 1 รูป และเลือกวิดีโอที่จะเบลอ')
    return
  }

  isProcessing.value = true
  errorMessage.value = ''
  statusMessage.value = ''
  resetPoller()

  try {
    await uploadReferenceFaces()
    const job = await submitBlurJob()
    processingStore.startJob({
      jobId: job.job_id,
      state: job.state,
      progress: 0,
      message: 'กำลังเตรียมงานประมวลผล...'
    })
    await pollJob(job.job_id)
  } catch (error) {
    if (!(error instanceof Error && error.message === errorMessage.value)) {
      errorMessage.value = extractErrorMessage(error)
    }
    processingStore.clearJob()
  } finally {
    isProcessing.value = false
  }
}

onBeforeUnmount(() => {
  resetPoller()
  referenceFaces.value.forEach((item) => URL.revokeObjectURL(item.previewUrl))
})
</script>

<template>
  <section class="grid gap-8">
    <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <h2 class="text-xl font-semibold text-white">1. แนบรูปหน้าของตัวเอง</h2>
      <p class="mt-2 text-sm text-slate-400">
        เราจะใช้รูปนี้เพื่อจดจำใบหน้าของคุณ และเว้นไม่ให้ถูกเบลอในทุกเฟรมของวิดีโอ
      </p>
      <label class="mt-4 flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-6 text-center text-slate-400 transition hover:border-slate-500 hover:text-slate-200">
        <span class="text-sm">คลิกหรือวางรูปภาพได้ครั้งละหลายไฟล์</span>
        <input
          class="hidden"
          type="file"
          accept="image/*"
          multiple
          @change="uploadReference(($event.target as HTMLInputElement).files)"
        />
        <span class="text-xs text-slate-500">แนะนำอัปโหลดมุมหน้าหลากหลายเพื่อความแม่นยำ</span>
      </label>
      <div v-if="referenceFaces.length" class="mt-4 grid gap-2">
        <p class="text-xs text-slate-400">รูปที่เลือกไว้ ({{ referenceFaces.length }})</p>
        <ul class="grid gap-2">
          <li
            v-for="item in referenceFaces"
            :key="item.id"
            class="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-2 text-sm"
          >
            <div class="flex items-center gap-3 overflow-hidden">
              <img :src="item.previewUrl" alt="preview" class="h-10 w-10 rounded object-cover" />
              <span class="max-w-[11rem] truncate text-slate-200">{{ item.file.name }}</span>
            </div>
            <button
              type="button"
              class="text-xs text-slate-400 transition hover:text-rose-300"
              @click.stop.prevent="removeReference(item.id)"
            >
              ลบ
            </button>
          </li>
        </ul>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <h2 class="text-xl font-semibold text-white">2. แนบวิดีโอที่ต้องการเบลอ</h2>
      <p class="mt-2 text-sm text-slate-400">
        รองรับไฟล์ MP4, MOV หรือ WebM ความยาวไม่เกิน 30 นาที (แนะนำไม่เกิน 2 GB ในเวอร์ชันทดลองนี้)
      </p>
      <label class="mt-4 flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-6 text-center text-slate-400 hover:border-slate-500 hover:text-slate-200">
        <span class="text-sm">คลิกหรือวางวิดีโอตรงนี้</span>
        <input class="hidden" type="file" accept="video/*" @change="selectVideo(($event.target as HTMLInputElement).files)" />
        <span class="text-xs text-slate-500">ระบบจะเตรียม progress bar ให้ระหว่างประมวลผล</span>
      </label>
      <div
        v-if="targetVideo"
        class="mt-4 flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-2 text-sm"
      >
        <div class="truncate">
          <p class="truncate font-medium text-slate-200">{{ targetVideo.name }}</p>
          <p class="text-xs text-slate-400">ขนาดไฟล์ประมาณ {{ formatBytes(targetVideo.size) }}</p>
        </div>
        <button
          type="button"
          class="text-xs text-slate-400 transition hover:text-rose-300"
          @click.prevent="clearVideo"
        >
          ลบไฟล์
        </button>
      </div>
    </div>

    <div class="grid gap-6 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 lg:grid-cols-[1fr_minmax(0,280px)]">
      <div class="flex flex-col gap-4">
        <div>
          <h2 class="text-xl font-semibold text-white">3. ปรับระดับความเบลอ</h2>
          <p class="mt-2 text-sm text-slate-400">
            เลื่อนเพื่อเลือกความเข้มจาก 1 (น้อยสุด) ถึง 10 (มากสุด)
          </p>
        </div>
        <input v-model="selectedBlur" type="range" min="1" max="10" class="w-full" />
        <p class="text-sm text-slate-300">ระดับปัจจุบัน: <strong>{{ selectedBlur }}</strong> (ประมาณ {{ previewLevel }}% ความเบลอ)</p>
      </div>
      <div class="rounded-xl border border-slate-800 bg-slate-950/80 p-4 text-center">
        <p class="text-sm text-slate-400">ตัวอย่างผลลัพธ์</p>
        <div class="mt-4 overflow-hidden rounded-lg border border-slate-800">
          <div class="relative h-40 w-full">
            <img
              :src="previewImageSrc"
              alt="blur preview"
              class="h-full w-full object-cover transition-all duration-300"
              :style="{ filter: `blur(${previewBlurPx}px)` }"
            />
            <div class="pointer-events-none absolute inset-0 border border-white/20 mix-blend-overlay" />
          </div>
          <p class="mt-2 text-xs text-slate-400">แสดงผลด้วยระดับความเบลอที่เลือก</p>
        </div>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <h2 class="text-xl font-semibold text-white">4. เลือกโหมดการประมวลผล</h2>
      <div class="mt-4 grid gap-4 md:grid-cols-2">
        <label class="flex cursor-pointer flex-col gap-2 rounded-xl border border-slate-700 bg-slate-900/50 p-4 hover:border-slate-500" :class="mode === 'fast' ? 'border-emerald-500 bg-emerald-500/10 text-emerald-200' : ''">
          <div class="flex items-center justify-between">
            <span class="text-lg font-medium">โหมดเร็ว</span>
            <input v-model="mode" type="radio" value="fast" />
          </div>
          <p class="text-sm">เน้นความเร็ว เหมาะสำหรับงานด่วน ภาพเบลอปานกลาง</p>
        </label>
        <label class="flex cursor-pointer flex-col gap-2 rounded-xl border border-slate-700 bg-slate-900/50 p-4 hover:border-slate-500" :class="mode === 'detailed' ? 'border-sky-500 bg-sky-500/10 text-sky-200' : ''">
          <div class="flex items-center justify-between">
            <span class="text-lg font-medium">โหมดละเอียด</span>
            <input v-model="mode" type="radio" value="detailed" />
          </div>
          <p class="text-sm">ใช้เวลานานขึ้น แต่ความเนียนและการติดตามใบหน้าดีกว่า</p>
        </label>
      </div>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <div class="text-sm text-slate-400">
        เมื่อพร้อมแล้ว กดปุ่มเพื่อเริ่มประมวลผล เราจะแสดงแถบสถานะและลิงก์ดาวน์โหลดเมื่อเสร็จ
      </div>
      <button
        class="rounded-full bg-emerald-500 px-6 py-3 text-sm font-semibold text-slate-900 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="isProcessing"
        @click="startProcessing"
      >
        {{ isProcessing ? 'กำลังประมวลผล...' : 'เริ่มเบลอวิดีโอ' }}
      </button>
    </div>

    <div v-if="jobStatus" class="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <div class="flex items-center justify-between">
        <p class="text-sm font-semibold text-slate-200">สถานะการประมวลผล</p>
        <span class="text-sm font-medium text-emerald-300">
          {{ displayProgress }}%
        </span>
      </div>
      <div class="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
        <div
          class="h-full bg-emerald-500 transition-all duration-500"
          :style="{ width: `${displayProgress}%` }"
        />
      </div>
      <p class="mt-3 text-sm text-slate-400">
        {{ jobStatus.message || 'ระบบกำลังประมวลผลวิดีโอของคุณ โปรดรอสักครู่...' }}
      </p>
      <div
        v-if="jobStatus.downloadUrl"
        class="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-3"
      >
        <p class="text-sm text-emerald-200">ไฟล์พร้อมให้ดาวน์โหลดแล้ว</p>
        <a
          :href="jobStatus.downloadUrl"
          download
          class="rounded-full bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-emerald-400"
        >
          ดาวน์โหลดวิดีโอ
        </a>
      </div>
      <p v-if="jobStatus.state === 'completed' && statusMessage" class="mt-3 text-sm text-emerald-400">
        {{ statusMessage }}
      </p>
      <p v-if="jobStatus.state === 'failed'" class="mt-3 text-sm text-rose-400">
        เกิดข้อผิดพลาดระหว่างการประมวลผล โปรดลองใหม่อีกครั้ง
      </p>
    </div>

    <div v-if="statusMessage && !jobStatus" class="rounded-xl border border-emerald-500/60 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
      {{ statusMessage }}
    </div>

    <div v-if="errorMessage" class="rounded-xl border border-rose-500/60 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
      {{ errorMessage }}
    </div>
  </section>
</template>
