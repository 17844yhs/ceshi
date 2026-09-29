<script setup>
import { computed, onMounted } from 'vue'
import { useDetectStore } from '../stores/detect'

const store = useDetectStore()
onMounted(() => { if (!store.report) store.loadReport() })

const m = computed(() => store.report?.metrics ?? {})
const c = computed(() => store.report?.confusion ?? {})
const pct = (v) => v != null ? (v * 100).toFixed(2) + '%' : '-'
</script>

<template>
  <div v-if="store.error" class="error-bar">{{ store.error }}</div>

  <template v-if="store.report">
    <div class="metric-grid">
      <div class="metric"><div class="v">{{ pct(m.accuracy) }}</div><div class="k">准确率 Accuracy</div></div>
      <div class="metric"><div class="v">{{ pct(m.recall) }}</div><div class="k">召回率 Recall（查全）</div></div>
      <div class="metric"><div class="v">{{ pct(m.precision) }}</div><div class="k">精确率 Precision（查准）</div></div>
      <div class="metric"><div class="v">{{ pct(m.type_alignment) }}</div><div class="k">分类对齐率</div></div>
    </div>

    <div class="card">
      <div class="toolbar"><span class="title">混淆矩阵（预测 × 人工标注）</span>
        <button class="btn ghost" :disabled="store.loading" @click="store.loadReport()">↻ 重算评测</button>
      </div>
      <div class="two-col" style="margin-top:14px">
        <div class="matrix">
          <div></div><div class="head">标注=幻觉</div><div class="head">标注=正常</div>
          <div class="head">预测=幻觉</div>
          <div class="cell good">{{ c.tp }}</div><div class="cell" :class="c.fp ? 'bad' : 'good'">{{ c.fp }}</div>
          <div class="head">预测=正常</div>
          <div class="cell" :class="c.fn ? 'bad' : 'good'">{{ c.fn }}</div><div class="cell good">{{ c.tn }}</div>
        </div>
        <div>
          <div class="kv small">TP 正确检出幻觉 · FP 误报（冤枉正常回复）</div>
          <div class="kv small">FN 漏检（放走幻觉）· TN 正确放行</div>
          <div class="kv small" style="margin-top:8px">
            <b>F1 = {{ pct(m.f1) }}</b>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar"><span class="title">逐条对比（{{ store.report.per_item.length }} 条）</span></div>
      <table style="margin-top:10px">
        <thead><tr>
          <th>ID</th><th>标注类型 (GT)</th><th>预测分类</th><th>二元判定</th><th>分类对齐</th><th>置信</th>
        </tr></thead>
        <tbody>
          <tr v-for="it in store.report.per_item" :key="it.id">
            <td><b>{{ it.id }}</b></td>
            <td>{{ it.gt_hallucination ? it.gt_type : '无幻觉' }}</td>
            <td>{{ it.pred_types?.join(' + ') || '-' }}</td>
            <td><span class="badge" :class="it.binary_match ? 'none' : 'critical'">{{ it.binary_match ? '一致' : '不一致' }}</span></td>
            <td><span v-if="it.gt_hallucination" class="badge" :class="it.type_match ? 'none' : 'review'">{{ it.type_match ? '对齐' : '偏差' }}</span><span v-else class="muted">-</span></td>
            <td>{{ (it.pred_confidence * 100).toFixed(0) }}%</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="two-col">
      <div class="card">
        <div class="toolbar"><span class="title">漏检清单（FN = {{ store.report.missed.length }}）</span></div>
        <div v-if="!store.report.missed.length" class="muted" style="margin-top:10px">无漏检</div>
        <div v-for="it in store.report.missed" :key="it.id" class="attribution-item" style="margin-top:10px">
          <b>{{ it.id }}</b>（标注：{{ it.gt_type }}）<br />
          <span class="small muted">归因：{{ it.attribution }}</span>
        </div>
      </div>
      <div class="card">
        <div class="toolbar"><span class="title">误报清单（FP = {{ store.report.false_positives.length }}）</span></div>
        <div v-if="!store.report.false_positives.length" class="muted" style="margin-top:10px">无误报</div>
        <div v-for="it in store.report.false_positives" :key="it.id" class="attribution-item ok" style="margin-top:10px">
          <b>{{ it.id }}</b>（预测：{{ it.pred_types?.join('+') }}）<br />
          <span class="small muted">归因：{{ it.attribution }}</span>
        </div>
      </div>
    </div>
  </template>
</template>
