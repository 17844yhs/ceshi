<script setup>
import { onMounted } from 'vue'
import { useDetectStore } from '../stores/detect'

const store = useDetectStore()
onMounted(() => { if (!store.results.length) store.runBatch() })
</script>

<template>
  <div v-if="store.error" class="error-bar">{{ store.error }}</div>

  <div class="card">
    <div class="toolbar">
      <span class="title">批量检测结果（data/task4_replies.json）</span>
      <button class="btn" :disabled="store.loading" @click="store.runBatch()">
        <span v-if="store.loading" class="spin">◌</span> {{ store.loading ? '检测中…' : '▶ 重新跑批' }}
      </button>
      <span class="muted small">点击行展开 证据对照</span>
    </div>
    <div class="chips">
      <div class="chip"><div class="num">{{ store.summary.total }}</div><div class="lab">检测总数</div></div>
      <div class="chip warn"><div class="num">{{ store.summary.hallucination_count }}</div><div class="lab">幻觉回复</div></div>
      <div class="chip ok"><div class="num">{{ store.summary.total - store.summary.hallucination_count }}</div><div class="lab">正常回复</div></div>
      <div class="chip review"><div class="num">{{ store.summary.needs_review_count }}</div><div class="lab">需人工复核</div></div>
    </div>
  </div>

  <div class="card">
    <table>
      <thead>
        <tr>
          <th style="width:56px">ID</th><th style="width:330px">客服回复</th>
          <th style="width:150px">分类</th><th style="width:90px">严重度</th>
          <th style="width:70px">置信度</th><th>备注</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="r in store.results" :key="r.id">
          <tr class="rowline" :class="{ expanded: store.expandedId === r.id }" @click="store.toggleExpand(r.id)">
            <td><b>{{ r.id }}</b></td>
            <td class="snippet">{{ r.reply || r.evidence?.[0] || '-' }}</td>
            <td>{{ r.type_labels?.join(' + ') || '-' }}</td>
            <td><span class="badge" :class="r.label === 'none' ? 'none' : r.severity">
              {{ r.label === 'none' ? '正常' : r.severity }}</span></td>
            <td>{{ (r.confidence * 100).toFixed(0) }}%</td>
            <td>
              <span v-if="r.partial" class="badge review">部分正确</span>
              <span v-if="r.needs_review" class="badge review">需人工复核</span>
              <span v-if="r.judge_fallback" class="badge ghost">裁判降级</span>
            </td>
          </tr>
          <tr v-if="store.expandedId === r.id">
            <td colspan="6">
              <div class="detail">
                <div class="kv"><b>用户问题：</b>{{ r.question }}</div>
                <div class="kv"><b>客服回复：</b>{{ r.reply }}</div>
                <div class="kv"><b>知识库：</b>{{ r.kb }}</div>
                <h4>证据对照</h4>
                <div v-for="(e, i) in r.evidence" :key="i" class="evidence">{{ e }}</div>
                <div v-if="!r.evidence?.length" class="muted small">规则层与裁判层均未发现 KB 冲突</div>
                <div class="kv small" style="margin-top:8px"><b>规则命中：</b>{{ r.rule_hits?.join('、') || '无' }}</div>
                <div class="kv small"><b>裁判层：</b>{{ r.judge_fallback ? '解析失败已降级（仅规则结果）' : (r.judge_raw?.engine === 'simulated' ? '模拟裁判（mock）' : 'LLM 裁判') }}</div>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
