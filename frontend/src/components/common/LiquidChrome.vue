<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Renderer, Program, Mesh, Triangle } from 'ogl'

const props = withDefaults(defineProps<{
  baseColor?: string; speed?: number; amplitude?: number; frequencyX?: number; frequencyY?: number; interactive?: boolean
}>(), {
  baseColor: '#0F0F0F', speed: 0.2, amplitude: 0.3, frequencyX: 3, frequencyY: 3, interactive: true,
})

const container = ref<HTMLDivElement>()
let renderer: Renderer | null = null, mesh: any = null, program: any = null, raf = 0

const hexToRgb = (hex: string): [number, number, number] => {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return m ? [parseInt(m[1],16)/255, parseInt(m[2],16)/255, parseInt(m[3],16)/255] : [0.1,0.1,0.1]
}

const vertexShader = `
  attribute vec2 position;
  attribute vec2 uv;
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position, 0.0, 1.0);
  }
`

const fragmentShader = `
  precision highp float;
  uniform float uTime;
  uniform vec3 uResolution;
  uniform vec3 uBaseColor;
  uniform float uAmplitude;
  uniform float uFrequencyX;
  uniform float uFrequencyY;
  uniform vec2 uMouse;
  varying vec2 vUv;

  vec4 renderImage(vec2 uvCoord) {
    vec2 fragCoord = uvCoord * uResolution.xy;
    vec2 uv = (2.0 * fragCoord - uResolution.xy) / min(uResolution.x, uResolution.y);

    for (float i = 1.0; i < 10.0; i++){
      uv.x += uAmplitude / i * cos(i * uFrequencyX * uv.y + uTime + uMouse.x * 3.14159);
      uv.y += uAmplitude / i * cos(i * uFrequencyY * uv.x + uTime + uMouse.y * 3.14159);
    }

    vec2 diff = (uvCoord - uMouse);
    float dist = length(diff);
    float falloff = exp(-dist * 20.0);
    float ripple = sin(10.0 * dist - uTime * 2.0) * 0.03;
    uv += (diff / (dist + 0.0001)) * ripple * falloff;

    vec3 color = uBaseColor / abs(sin(uTime - uv.y - uv.x));
    return vec4(color, 1.0);
  }

  void main() {
    vec4 col = vec4(0.0);
    int samples = 0;
    for (int i = -1; i <= 1; i++){
      for (int j = -1; j <= 1; j++){
        vec2 offset = vec2(float(i), float(j)) * (1.0 / min(uResolution.x, uResolution.y));
        col += renderImage(vUv + offset);
        samples++;
      }
    }
    gl_FragColor = col / float(samples);
  }
`

function init() {
  if (!container.value) return
  const el = container.value
  renderer = new Renderer({ alpha: true, antialias: true, dpr: Math.min(window.devicePixelRatio || 1, 2) })
  const gl = renderer.gl
  gl.clearColor(1, 1, 1, 1)
  gl.canvas.style.display = 'block'
  gl.canvas.style.width = '100%'
  gl.canvas.style.height = '100%'
  el.appendChild(gl.canvas)

  const rgb = hexToRgb(props.baseColor)
  const geometry = new Triangle(gl)
  program = new Program(gl, {
    vertex: vertexShader,
    fragment: fragmentShader,
    uniforms: {
      uTime: { value: 0 },
      uResolution: { value: new Float32Array([1, 1, 1]) },
      uBaseColor: { value: new Float32Array(rgb) },
      uAmplitude: { value: props.amplitude },
      uFrequencyX: { value: props.frequencyX },
      uFrequencyY: { value: props.frequencyY },
      uMouse: { value: new Float32Array([0.5, 0.5]) },
    }
  })
  mesh = new Mesh(gl, { geometry, program })

  function resize() {
    if (!renderer) return
    renderer.setSize(Math.max(1, el.clientWidth), Math.max(1, el.clientHeight))
    const resUniform = program.uniforms.uResolution.value
    resUniform[0] = gl.drawingBufferWidth
    resUniform[1] = gl.drawingBufferHeight
    resUniform[2] = gl.drawingBufferWidth / gl.drawingBufferHeight
  }
  window.addEventListener('resize', resize)
  resize()

  function handleMouseMove(e: MouseEvent) {
    const rect = el.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = 1 - (e.clientY - rect.top) / rect.height
    program.uniforms.uMouse.value.set([x, y])
  }
  function handleTouchMove(e: TouchEvent) {
    if (e.touches.length > 0) {
      const t = e.touches[0]
      const rect = el.getBoundingClientRect()
      const x = (t.clientX - rect.left) / rect.width
      const y = 1 - (t.clientY - rect.top) / rect.height
      program.uniforms.uMouse.value.set([x, y])
    }
  }
  if (props.interactive) {
    el.addEventListener('mousemove', handleMouseMove)
    el.addEventListener('touchmove', handleTouchMove)
  }

  function update(t: number) {
    raf = requestAnimationFrame(update)
    program.uniforms.uTime.value = t * 0.001 * props.speed
    renderer!.render({ scene: mesh })
  }
  raf = requestAnimationFrame(update)
}

onMounted(init)
onUnmounted(() => {
  cancelAnimationFrame(raf)
  if (renderer) {
    const gl = renderer.gl
    if (gl.canvas.parentElement) gl.canvas.parentElement.removeChild(gl.canvas)
    gl.getExtension('WEBGL_lose_context')?.loseContext()
  }
})
</script>

<template>
  <div ref="container" class="liquid-chrome-bg"></div>
</template>

<style scoped>
.liquid-chrome-bg {
  position: absolute; inset: 0; overflow: hidden; pointer-events: none;
  z-index: 0;
}
</style>
