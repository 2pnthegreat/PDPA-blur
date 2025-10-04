import { defineStore } from 'pinia'

export type JobState = 'pending' | 'running' | 'completed' | 'failed'

export interface ProcessingJob {
  jobId: string
  state: JobState
  progress: number
  message?: string
  downloadUrl?: string
}

export const useProcessingStore = defineStore('processing', {
  state: () => ({
    currentJob: null as ProcessingJob | null
  }),
  actions: {
    startJob(job: ProcessingJob) {
      this.currentJob = job
    },
    updateJob(partial: Partial<ProcessingJob>) {
      if (!this.currentJob) return
      this.currentJob = { ...this.currentJob, ...partial }
    },
    clearJob() {
      this.currentJob = null
    }
  }
})
