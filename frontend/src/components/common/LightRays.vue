<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Renderer, Program, Triangle, Mesh } from 'ogl'

const props = withDefaults(defineProps<{
  raysOrigin?: string; raysColor?: string; raysSpeed?: number
  lightSpread?: number; rayLength?: number; pulsating?: boolean
  fadeDistance?: number; saturation?: number
  followMouse?: boolean; mouseInfluence?: number
  noiseAmount?: number; distortion?: number
}>(), {
  raysOrigin: 'top-center', raysColor: '#2F65FF', raysSpeed: 0.6,
  lightSpread: 0.5, rayLength: 1.5, pulsating: false,
  fadeDistance: 1.0, saturation: 1.0,
  followMouse: true, mouseInfluence: 0.08,
  noiseAmount: 0, distortion: 0,
})

const container = ref<HTMLDivElement>()
let renderer: Renderer | null = null, uniforms: Record<string, any> = {}, mesh: any = null, animId = 0
let mouseRef = { x: 0.5, y: 0.5 }, smoothMouse = { x: 0.5, y: 0.5 }

const hexToRgb = (h: string): [number,number,number] => {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(h)
  return m ? [parseInt(m[1],16)/255, parseInt(m[2],16)/255, parseInt(m[3],16)/255] : [1,1,1]
}
const getAnchorDir = (o: string, w: number, h: number) => {
  const out = 0.2
  switch(o){
    case 'top-left': return {a:[0,-out*h],d:[0,1]}
    case 'top-right': return {a:[w,-out*h],d:[0,1]}
    case 'left': return {a:[-out*w,.5*h],d:[1,0]}
    case 'right': return {a:[(1+out)*w,.5*h],d:[-1,0]}
    case 'bottom-left': return {a:[0,(1+out)*h],d:[0,-1]}
    case 'bottom-center': return {a:[.5*w,(1+out)*h],d:[0,-1]}
    case 'bottom-right': return {a:[w,(1+out)*h],d:[0,-1]}
    default: return {a:[.5*w,-out*h],d:[0,1]}
  }
}

const vert = `attribute vec2 position; varying vec2 vUv;
void main(){ vUv=position*.5+.5; gl_Position=vec4(position,0.,1.); }`

const frag = `precision highp float;
uniform float iTime; uniform vec2 iResolution;
uniform vec2 rayPos, rayDir, mousePos;
uniform vec3 raysColor;
uniform float raysSpeed, lightSpread, rayLength, pulsating, fadeDistance, saturation, mouseInfluence, noiseAmount, distortion;
varying vec2 vUv;

float noise(vec2 st){ return fract(sin(dot(st,vec2(12.9898,78.233)))*43758.5453); }

float rayStrength(vec2 src, vec2 refDir, vec2 coord, float sa, float sb, float spd){
  vec2 dc=coord-src; vec2 dn=normalize(dc);
  float ca=dot(dn,refDir);
  ca+=distortion*sin(iTime*2.+length(dc)*.01)*.2;
  float sf=pow(max(ca,0.),1./max(lightSpread,.001));
  float dist=length(dc), md=iResolution.x*rayLength;
  float lf=clamp((md-dist)/md,0.,1.);
  float ff=clamp((iResolution.x*fadeDistance-dist)/(iResolution.x*fadeDistance),.5,1.);
  float pulse=pulsating>.5?(.8+.2*sin(iTime*spd*3.)):1.;
  return clamp((.45+.15*sin(ca*sa+iTime*spd))+(.3+.2*cos(-ca*sb+iTime*spd)),0.,1.)*lf*ff*sf*pulse;
}

void main(){
  vec2 coord=vec2(gl_FragCoord.x,iResolution.y-gl_FragCoord.y);
  vec2 finalDir=rayDir;
  if(mouseInfluence>0.){
    vec2 ms=mousePos*iResolution.xy;
    finalDir=normalize(mix(rayDir,normalize(ms-rayPos),mouseInfluence));
  }
  vec4 c=vec4(1.)*rayStrength(rayPos,finalDir,coord,36.22,21.11,1.5*raysSpeed)*.5
       +vec4(1.)*rayStrength(rayPos,finalDir,coord,22.40,18.02,1.1*raysSpeed)*.4;
  if(noiseAmount>0.){float n=noise(coord*.01+iTime*.1);c.rgb*=(1.-noiseAmount+noiseAmount*n);}
  float br=1.-(coord.y/iResolution.y);
  c.x*=.1+br*.8; c.y*=.3+br*.6; c.z*=.5+br*.5;
  if(saturation!=1.){float g=dot(c.rgb,vec3(.299,.587,.114));c.rgb=mix(vec3(g),c.rgb,saturation);}
  c.rgb*=raysColor;
  gl_FragColor=c;
}`

onMounted(() => {
  if(!container.value) return
  const el=container.value
  renderer=new Renderer({dpr:Math.min(devicePixelRatio,2),alpha:true})
  const gl=renderer.gl; gl.canvas.style.width='100%'; gl.canvas.style.height='100%'
  el.appendChild(gl.canvas)
  uniforms={
    iTime:{value:0},iResolution:{value:[1,1]},rayPos:{value:[0,0]},rayDir:{value:[0,1]},
    raysColor:{value:hexToRgb(props.raysColor)},raysSpeed:{value:props.raysSpeed},
    lightSpread:{value:props.lightSpread},rayLength:{value:props.rayLength},
    pulsating:{value:props.pulsating?1:0},fadeDistance:{value:props.fadeDistance},
    saturation:{value:props.saturation},mousePos:{value:[.5,.5]},
    mouseInfluence:{value:props.mouseInfluence},noiseAmount:{value:props.noiseAmount},
    distortion:{value:props.distortion},
  }
  const geom=new Triangle(gl), prog=new Program(gl,{vertex:vert,fragment:frag,uniforms})
  mesh=new Mesh(gl,{geometry:geom,program:prog})
  const resize=()=>{
    if(!renderer||!el)return
    renderer.dpr=Math.min(devicePixelRatio,2)
    const w=el.clientWidth*renderer.dpr, h=el.clientHeight*renderer.dpr
    renderer.setSize(el.clientWidth,el.clientHeight)
    uniforms.iResolution.value=[w,h]
    const {a,d}=getAnchorDir(props.raysOrigin,w,h)
    uniforms.rayPos.value=a; uniforms.rayDir.value=d
  }
  window.addEventListener('resize',resize); resize()
  const loop=(t:number)=>{
    uniforms.iTime.value=t*.001
    if(props.followMouse&&props.mouseInfluence>0){
      smoothMouse.x=smoothMouse.x*.92+mouseRef.x*.08
      smoothMouse.y=smoothMouse.y*.92+mouseRef.y*.08
      uniforms.mousePos.value=[smoothMouse.x,smoothMouse.y]
    }
    renderer?.render({scene:mesh}); animId=requestAnimationFrame(loop)
  }
  animId=requestAnimationFrame(loop)
  const onMouse=(e:MouseEvent)=>{if(!el)return;const r=el.getBoundingClientRect();mouseRef={x:(e.clientX-r.left)/r.width,y:(e.clientY-r.top)/r.height}}
  window.addEventListener('mousemove',onMouse)
  onUnmounted(()=>{cancelAnimationFrame(animId);window.removeEventListener('resize',resize);window.removeEventListener('mousemove',onMouse);renderer=null;mesh=null})
})
</script>

<template><div ref="container" class="light-rays" /></template>

<style scoped>
.light-rays { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
</style>
