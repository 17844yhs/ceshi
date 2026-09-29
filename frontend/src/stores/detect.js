import { defineStore } from 'pinia'
import { api } from '../api/client'

export const useDetectStore = defineStore('detect', {
  state: () => ({
    mode: 'mock',
    results: [],
    summary: { total: 0, hallucination_count: 0, needs_review_count: 0 },
    report: null,
    loading: false,
    error: '',
    expandedId: null,
  }),
  getters: {
    byId: (s) => Object.fromEntries(s.results.map((r) => [r.id, r])),
  },
  actions: {
    async init() {
      try {
        const h = await api.health()
        this.mode = h.mode
      } catch {
        this.error = '后端不可用：请先启动 backend（uv run python -m app.main）'
      }
    },
    async runBatch() {
      this.loading = true
      this.error = ''
      try {
        const data = await api.batch()
        this.results = data.results
        this.summary = {
          total: data.total,
          hallucination_count: data.hallucination_count,
          needs_review_count: data.needs_review_count,
        }
      } catch (e) {
        this.error = e.message
      } finally {
        this.loading = false
      }
    },
    async loadReport() {
      this.loading = true
      this.error = ''
      try {
        this.report = await api.eval()
        this.results = this.report.per_item ? this.results : this.results
      } catch (e) {
        this.error = e.message
      } finally {
        this.loading = false
      }
    },
    toggleExpand(id) {
      this.expandedId = this.expandedId === id ? null : id
    },
  },
})
