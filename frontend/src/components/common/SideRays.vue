<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Renderer, Program, Triangle, Mesh } from 'ogl'

const props = withDefaults(defineProps<{
  speed?: number; rayColor1?: string; rayColor2?: string
  intensity?: number; spread?: number; origin?: string; tilt?: number
  saturation?: number; blend?: number; falloff?: number; opacity?: number
}>(), {
  speed: 2.5, rayColor1: '#EAB308', rayColor2: '#96c8ff',
  intensity: 2, spread: 2, origin: 'top-right', tilt: 0,
  saturation: 1.5, blend: 0.75, falloff: 1.6, opacity: 1,
})

const container = ref<HTMLDivElement>()
let renderer: Renderer | null = null, mesh: any = null, uniforms: Record<string, any> = {}, raf = 0
let cleanup: (() => void) | null = null

const hexToRgb = (h: string): [number,number,number] => {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(h)
  return m ? [parseInt(m[1],16)/255, parseInt(m[2],16)/255, parseInt(m[3],16)/255] : [1,1,1]
}
const originFlip = (o: string): [number,number] => {
  switch(o) { case 'top-left': return [1,0]; case 'bottom-right': return [0,1]; case 'bottom-left': return [1,1]; default: return [0,0] }
}

const vert = `attribute vec2 position; void main(){gl_Position=vec4(position,0.,1.);}`
const frag = `precision highp float;
uniform float iTime; uniform vec2 iResolution; uniform float iSpeed;
uniform vec3 iRayColor1, iRayColor2; uniform float iIntensity, iSpread, iFlipX, iFlipY, iTilt, iSaturation, iBlend, iFalloff, iOpacity;
float rs(vec2 src,vec2 rd,vec2 c,float sa,float sb,float s){
  vec2 dc=c-src; float ca=dot(normalize(dc),rd);
  return clamp((.45+.15*sin(ca*sa+iTime*s))+(.3+.2*cos(-ca*sb+iTime*s)),0.,1.)*clamp((iResolution.x-length(dc))/iResolution.x,.5,1.);
}
void main(){
  vec2 fc=gl_FragCoord.xy;
  if(iFlipX>.5)fc.x=iResolution.x-fc.x;
  if(iFlipY>.5)fc.y=iResolution.y-fc.y;
  vec2 c=vec2(fc.x,iResolution.y-fc.y);
  vec2 rp=vec2(iResolution.x*1.1,-.5*iResolution.y);
  float tr=iTilt*3.14159265/180.,cs=cos(tr),sn=sin(tr);
  vec2 rel=c-rp,tc=vec2(rel.x*cs-rel.y*sn,rel.x*sn+rel.y*cs)+rp;
  float hs=iSpread*.275;
  vec2 rd1=normalize(vec2(cos(.785398+hs),sin(.785398+hs)));
  vec2 rd2=normalize(vec2(cos(.785398-hs),sin(.785398-hs)));
  vec4 r1=vec4(iRayColor1,1.)*rs(rp,rd1,tc,36.22,21.11,iSpeed);
  vec4 r2=vec4(iRayColor2,1.)*rs(rp,rd2,tc,22.40,18.02,iSpeed*.2);
  vec4 co=r1*(1.-iBlend)*.9+r2*iBlend*.9;
  float d=length(fc.xy-vec2(rp.x,iResolution.y-rp.y))/iResolution.y;
  co.rgb*=iIntensity*.4/pow(max(d,.001),iFalloff);
  float g=dot(co.rgb,vec3(.299,.587,.114));
  co.rgb=mix(vec3(g),co.rgb,iSaturation);
  co.a=max(co.r,max(co.g,co.b))*iOpacity;
  gl_FragColor=co;
}`

onMounted(() => {
  if(!container.value) return
  const el=container.value
  renderer=new Renderer({dpr:Math.min(devicePixelRatio,2),alpha:true})
  const gl=renderer.gl; gl.canvas.style.width='100%'; gl.canvas.style.height='100%'; el.appendChild(gl.canvas)
  const [fx,fy]=originFlip(props.origin)
  uniforms={
    iTime:{value:0},iResolution:{value:[1,1]},iSpeed:{value:props.speed},
    iRayColor1:{value:hexToRgb(props.rayColor1)},iRayColor2:{value:hexToRgb(props.rayColor2)},
    iIntensity:{value:props.intensity},iSpread:{value:props.spread},
    iFlipX:{value:fx},iFlipY:{value:fy},iTilt:{value:props.tilt},
    iSaturation:{value:props.saturation},iBlend:{value:props.blend},
    iFalloff:{value:props.falloff},iOpacity:{value:props.opacity},
  }
  const geom=new Triangle(gl), prog=new Program(gl,{vertex:vert,fragment:frag,uniforms})
  mesh=new Mesh(gl,{geometry:geom,program:prog})
  const resize=()=>{
    if(!renderer||!el)return
    renderer.dpr=Math.min(devicePixelRatio,2)
    const w=el.clientWidth*renderer.dpr, h=el.clientHeight*renderer.dpr
    renderer.setSize(el.clientWidth,el.clientHeight); uniforms.iResolution.value=[w,h]
  }
  window.addEventListener('resize',resize); resize()
  const loop=(t:number)=>{uniforms.iTime.value=t*.001;renderer!.render({scene:mesh});raf=requestAnimationFrame(loop)}
  raf=requestAnimationFrame(loop)
  cleanup=()=>{cancelAnimationFrame(raf);window.removeEventListener('resize',resize);renderer=null;mesh=null}
  onUnmounted(()=>cleanup?.())
})
</script>

<template><div ref="container" class="side-rays" /></template>

<style scoped>
.side-rays { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
</style>
