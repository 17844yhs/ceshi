<script setup>
import { onMounted } from 'vue'
import { useDetectStore } from './stores/detect'

const store = useDetectStore()
onMounted(() => store.init())
</script>

<template>
  <header class="app-header">
    <div class="logo">Hallu<span>Guard</span> · 客服回复幻觉检测</div>
    <nav>
      <router-link to="/detect">检测看板</router-link>
      <router-link to="/report">评测报告</router-link>
    </nav>
    <div class="mode-chip">裁判模式：{{ store.mode === 'mock' ? 'MOCK（模拟）' : 'REAL（LLM）' }}</div>
  </header>
  <main class="page">
    <router-view />
  </main>
</template>
