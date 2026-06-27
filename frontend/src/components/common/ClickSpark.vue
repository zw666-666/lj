<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  sparkColor?: string
  sparkSize?: number
  sparkRadius?: number
  sparkCount?: number
  duration?: number
}>(), {
  sparkColor: '#58A6FF',
  sparkSize: 8,
  sparkRadius: 20,
  sparkCount: 8,
  duration: 500,
})

const container = ref<HTMLDivElement>()
const canvas = ref<HTMLCanvasElement>()
const sparks: { x: number; y: number; angle: number; startTime: number }[] = []
let animId = 0

function resize() {
  if (!canvas.value || !container.value) return
  const { width, height } = container.value.getBoundingClientRect()
  canvas.value.width = width
  canvas.value.height = height
}

onMounted(() => {
  resize()
  window.addEventListener('resize', resize)
  animId = requestAnimationFrame(draw)
})

onUnmounted(() => {
  cancelAnimationFrame(animId)
  window.removeEventListener('resize', resize)
})

function draw(ts: number) {
  const c = canvas.value
  if (!c) { animId = requestAnimationFrame(draw); return }
  const ctx = c.getContext('2d')!
  ctx.clearRect(0, 0, c.width, c.height)

  for (let i = sparks.length - 1; i >= 0; i--) {
    const s = sparks[i]
    const elapsed = ts - s.startTime
    if (elapsed >= props.duration) { sparks.splice(i, 1); continue }
    const t = elapsed / props.duration
    const eased = t * (2 - t)
    const d = eased * props.sparkRadius
    const len = props.sparkSize * (1 - eased)
    const x1 = s.x + d * Math.cos(s.angle)
    const y1 = s.y + d * Math.sin(s.angle)
    const x2 = s.x + (d + len) * Math.cos(s.angle)
    const y2 = s.y + (d + len) * Math.sin(s.angle)
    ctx.strokeStyle = props.sparkColor
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()
  }
  animId = requestAnimationFrame(draw)
}

function onClick(e: MouseEvent) {
  if (!canvas.value) return
  const rect = canvas.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  const now = performance.now()
  for (let i = 0; i < props.sparkCount; i++) {
    sparks.push({ x, y, angle: (2 * Math.PI * i) / props.sparkCount, startTime: now })
  }
}
</script>

<template>
  <div ref="container" class="click-spark-container" @click="onClick">
    <canvas ref="canvas" class="click-spark-canvas" />
    <slot />
  </div>
</template>

<style scoped>
.click-spark-container { position: relative; width: 100%; height: 100%; }
.click-spark-canvas {
  position: absolute; inset: 0; pointer-events: none; z-index: 9999;
  display: block; user-select: none;
}
</style>
