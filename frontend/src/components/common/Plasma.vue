<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Renderer, Program, Mesh, Triangle } from 'ogl'

const props = withDefaults(defineProps<{
  color?: string; speed?: number; direction?: string; scale?: number; opacity?: number; mouseInteractive?: boolean
}>(), {
  color: '', speed: 1, direction: 'forward', scale: 1, opacity: 1, mouseInteractive: true,
})

const container = ref<HTMLDivElement>()
let renderer: Renderer | null = null, mesh: any = null, program: any = null, raf = 0
let mouse = { x: 0, y: 0 }, isVisible = true, contextLost = false

const hexToRgb = (hex: string): [number, number, number] => {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return m ? [parseInt(m[1],16)/255, parseInt(m[2],16)/255, parseInt(m[3],16)/255] : [1,1,1]
}

const vert = `#version 300 es
precision highp float; in vec2 position; in vec2 uv; out vec2 vUv;
void main(){vUv=uv;gl_Position=vec4(position,0.,1.);}`

const frag = `#version 300 es
precision highp float;
uniform vec2 iResolution; uniform float iTime;
uniform vec3 uCustomColor; uniform float uUseCustomColor;
uniform float uSpeed, uDirection, uScale, uOpacity;
uniform vec2 uMouse; uniform float uMouseInteractive;
out vec4 fragColor;

void mainImage(out vec4 o, vec2 C){
  vec2 center=iResolution.xy*.5;
  C=(C-center)/uScale+center;
  vec2 mOff=(uMouse-center)*.0002;
  C+=mOff*length(C-center)*step(.5,uMouseInteractive);
  float i,d,z,T=iTime*uSpeed*uDirection; vec3 O,p,S;
  for(vec2 r=iResolution.xy,Q;++i<60.;O+=o.w/d*o.xyz){
    p=z*normalize(vec3(C-.5*r,r.y));p.z-=4.;S=p;d=p.y-T;
    p.x+=.4*(1.+p.y)*sin(d+p.x*.1)*cos(.34*d+p.x*.05);
    Q=p.xz*=mat2(cos(p.y+vec4(0,11,33,0)-T));
    z+=d=abs(sqrt(length(Q*Q))-.25*(5.+S.y))/3.+8e-4;
    o=1.+sin(S.y+p.z*.5+S.z-length(S-p)+vec4(2,1,0,8));
  }
  o.xyz=tanh(O/1e4);
}
vec3 sani(vec3 c){return vec3(isnan(c.r)||isinf(c.r)?0.:c.r,isnan(c.g)||isinf(c.g)?0.:c.g,isnan(c.b)||isinf(c.b)?0.:c.b);}
void main(){
  vec4 o=vec4(0.);mainImage(o,gl_FragCoord.xy);
  vec3 rgb=sani(o.rgb);
  float intensity=(rgb.r+rgb.g+rgb.b)/3.;
  vec3 cc=intensity*uCustomColor;
  vec3 fc=mix(rgb,cc,step(.5,uUseCustomColor));
  fragColor=vec4(fc,length(rgb)*uOpacity);
}`

function init() {
  if (!container.value) return
  const el = container.value
  renderer = new Renderer({ webgl: 2, alpha: true, antialias: false, dpr: Math.min(devicePixelRatio || 1, 2) })
  const gl = renderer.gl
  gl.canvas.style.display = 'block'; gl.canvas.style.width = '100%'; gl.canvas.style.height = '100%'
  el.appendChild(gl.canvas)

  const useCC = props.color ? 1. : 0.
  const ccRgb = props.color ? hexToRgb(props.color) : [1,1,1]
  const dirMul = props.direction === 'reverse' ? -1. : 1.

  const geom = new Triangle(gl)
  program = new Program(gl, { vertex: vert, fragment: frag, uniforms: {
    iTime: { value: 0 }, iResolution: { value: new Float32Array([1,1]) },
    uCustomColor: { value: new Float32Array(ccRgb) }, uUseCustomColor: { value: useCC },
    uSpeed: { value: props.speed * 0.4 }, uDirection: { value: dirMul },
    uScale: { value: props.scale }, uOpacity: { value: props.opacity },
    uMouse: { value: new Float32Array([0,0]) }, uMouseInteractive: { value: props.mouseInteractive ? 1. : 0. },
  }})
  mesh = new Mesh(gl, { geometry: geom, program })

  const resize = () => { const r = el.getBoundingClientRect(); renderer!.setSize(Math.max(1,r.width), Math.max(1,r.height)); program.uniforms.iResolution.value.set([gl.drawingBufferWidth, gl.drawingBufferHeight]) }
  new ResizeObserver(resize).observe(el); resize()
  const t0 = performance.now()

  const loop = (t: number) => {
    if (contextLost || !isVisible) return
    let tv = (t - t0) * 0.001
    if (props.direction === 'pingpong') {
      const dur = 10, seg = tv % dur, fwd = Math.floor(tv / dur) % 2 === 0
      tv = fwd ? seg : dur - seg
    }
    program.uniforms.iTime.value = tv
    renderer!.render({ scene: mesh }); raf = requestAnimationFrame(loop)
  }
  raf = requestAnimationFrame(loop)

  const onMouse = (e: MouseEvent) => { const r = el.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; program.uniforms.uMouse.value.set([mouse.x, mouse.y]) }
  el.addEventListener('mousemove', onMouse)

  onUnmounted(() => { cancelAnimationFrame(raf); el.removeEventListener('mousemove', onMouse); renderer = null; mesh = null })
}

onMounted(init)
</script>

<template><div ref="container" class="plasma-bg" /></template>

<style scoped>
.plasma-bg { position: absolute; top: 0; left: -50%; width: 150%; height: 100%; overflow: hidden; z-index: 0; }
</style>
