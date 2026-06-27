<script setup lang="ts">
import { RouterView } from "vue-router"
import ClickSpark from "@/components/common/ClickSpark.vue"
</script>

<template>
  <ClickSpark spark-color="#58A6FF" :spark-size="6" :spark-radius="18" :spark-count="6" :duration="500">
    <RouterView />
  </ClickSpark>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

html {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
  background: #0F0F0F;
  color: #1a2744;
  min-height: 100vh;
  line-height: 1.6;
}

/* ——— 全局动画 ——— */
@keyframes fade-up {
  from { opacity: 0; transform: translateY(16px); filter: blur(4px); }
  to   { opacity: 1; transform: translateY(0);    filter: blur(0); }
}

@keyframes fade-down {
  from { opacity: 0; transform: translateY(-12px); }
  to   { opacity: 1; transform: translateY(0); }
}

.animate-fade-up {
  animation: fade-up 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.animate-fade-down {
  animation: fade-down 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@media (prefers-reduced-motion: reduce) {
  .animate-fade-up,
  .animate-fade-down,
  * { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
}
</style>
