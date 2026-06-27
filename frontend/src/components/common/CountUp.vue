<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'

const props = withDefaults(defineProps<{
  to: number
  from?: number
  duration?: number
  delay?: number
  separator?: string
}>(), {
  from: 0,
  duration: 1.2,
  delay: 0,
  separator: ',',
})

const display = ref('0')
let raf = 0

function easeOutExpo(t: number) { return t === 1 ? 1 : 1 - Math.pow(2, -10 * t) }

function format(n: number): string {
  const fixed = n.toFixed(0)
  if (props.separator) {
    return fixed.replace(/\B(?=(\d{3})+(?!\d))/g, props.separator)
  }
  return fixed
}

function animate() {
  const start = performance.now()
  display.value = format(props.from)

  function tick(now: number) {
    const elapsed = now - start - props.delay * 1000
    if (elapsed < 0) { raf = requestAnimationFrame(tick); return }
    const progress = Math.min(elapsed / (props.duration * 1000), 1)
    const val = props.from + (props.to - props.from) * easeOutExpo(progress)
    display.value = format(val)
    if (progress < 1) raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
}

onMounted(() => animate())
watch(() => props.to, () => { cancelAnimationFrame(raf); animate() })
</script>

<template>
  <span><slot :value="display">{{ display }}</slot></span>
</template>
