<script setup lang="ts">
import { ref, onMounted } from "vue"
import { useRouter } from "vue-router"
import api from "@/api/client"
import SideRays from "@/components/common/SideRays.vue"

const router = useRouter()
const featuredCases = ref<any[]>([])
const featuredJudges = ref<any[]>([])
const loaded = ref(false)

onMounted(async () => {
  try {
    const caseRes = await api.post("/search/semantic", {
      query: "民事纠纷 合同纠纷 刑事", mode: "semantic", page_size: 6,
    })
    featuredCases.value = (caseRes.data?.results || []).slice(0, 6)
  } catch { featuredCases.value = [] }
  setTimeout(() => { loaded.value = true }, 100)
})

function goSearch() { router.push("/home") }
function goCase(id: number) { router.push(`/case/${id}`) }
function goJudge(name: string) { router.push(`/profile/judge/${encodeURIComponent(name)}`) }
</script>

<template>
  <div class="landing" :class="{ loaded }">
    <SideRays :speed="2.0" ray-color1="#2F65FF" ray-color2="#58A6FF" :intensity="2.5" :spread="1.8" origin="top-right" :saturation="1.5" :blend="0.6" :falloff="1.2" :opacity="0.7" />
    <div class="landing-inner">
    <!-- Hero -->
    <section class="hero">
      <div class="hero-aura"></div>
      <div class="hero-line"></div>
      <span class="hero-mark">&#x2696;</span>
      <div class="hero-text">
        <h1>律 镜</h1>
        <p class="hero-sub">以数为镜，洞察裁判之律</p>
      </div>
      <p class="hero-desc">AI 驱动的智能法律检索平台<br>从 1.4 亿公开裁判文书中精准找到您需要的案例</p>
      <button class="hero-btn" @click="goSearch">
        <div class="btn-state">
          <div class="btn-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M14.2199 21.63C13.0399 21.63 11.3699 20.8 10.0499 16.83L9.32988 14.67L7.16988 13.95C3.20988 12.63 2.37988 10.96 2.37988 9.78001C2.37988 8.61001 3.20988 6.93001 7.16988 5.60001L15.6599 2.77001C17.7799 2.06001 19.5499 2.27001 20.6399 3.35001C21.7299 4.43001 21.9399 6.21001 21.2299 8.33001L18.3999 16.82C17.0699 20.8 15.3999 21.63 14.2199 21.63ZM7.63988 7.03001C4.85988 7.96001 3.86988 9.06001 3.86988 9.78001C3.86988 10.5 4.85988 11.6 7.63988 12.52L10.1599 13.36C10.3799 13.43 10.5599 13.61 10.6299 13.83L11.4699 16.35C12.3899 19.13 13.4999 20.12 14.2199 20.12C14.9399 20.12 16.0399 19.13 16.9699 16.35L19.7999 7.86001C20.3099 6.32001 20.2199 5.06001 19.5699 4.41001C18.9199 3.76001 17.6599 3.68001 16.1299 4.19001L7.63988 7.03001Z" fill="currentColor"></path>
              <path d="M10.11 14.4C9.92005 14.4 9.73005 14.33 9.58005 14.18C9.29005 13.89 9.29005 13.41 9.58005 13.12L13.16 9.53C13.45 9.24 13.93 9.24 14.22 9.53C14.51 9.82 14.51 10.3 14.22 10.59L10.64 14.18C10.5 14.33 10.3 14.4 10.11 14.4Z" fill="currentColor"></path>
            </svg>
          </div>
          <p>
            <span style="--i:0">开</span>
            <span style="--i:1">始</span>
            <span style="--i:2">探</span>
            <span style="--i:3">索</span>
          </p>
        </div>
      </button>
    </section>

    <!-- 知名案例 -->
    <section v-if="featuredCases.length" class="section">
      <div class="sec-head">
        <span class="sec-line"></span>
        <h2>知名案例</h2>
      </div>
      <div class="case-grid">
        <div v-for="(c, i) in featuredCases" :key="c.id" class="case-card" :style="{ animationDelay: `${0.1 + i * 0.06}s` }" @click="goCase(c.id)">
          <span class="cc-no">{{ c.case_no }}</span>
          <span class="cc-title">{{ (c.title || c.case_no).slice(0, 28) }}</span>
          <span class="cc-court">{{ c.court }}</span>
          <span class="cc-summary">{{ (c.ai_summary || '').slice(0, 60) }}</span>
        </div>
      </div>
    </section>

    <!-- 知名法官 -->
    <section v-if="featuredJudges.length" class="section">
      <div class="sec-head">
        <span class="sec-line"></span>
        <h2>知名法官</h2>
      </div>
      <div class="judge-grid">
        <div v-for="(j, i) in featuredJudges" :key="j.id" class="judge-card" :style="{ animationDelay: `${0.1 + i * 0.06}s` }" @click="goJudge(j.name || '')">
          <span class="jc-icon">&#x2696;</span>
          <span class="jc-name">{{ j.name }}</span>
          <span class="jc-court">{{ j.court }}</span>
          <span class="jc-stats">{{ j.case_count || 0 }} 件 · 改判 {{ j.appeal_rate ? (j.appeal_rate * 100).toFixed(0) : '?' }}%</span>
        </div>
      </div>
    </section>

    <footer class="landing-footer">© 2026 律镜 LawMirror</footer>
    </div>
  </div>
</template>

<style scoped>
.landing { padding: 0 20px 20px; min-height: 100vh; margin-top: -24px; }
.landing-inner { max-width: 960px; margin: 0 auto; }

/* ====== Hero ====== */
.hero {
  text-align: center; padding: 0 0 30px; position: relative;
  display: flex; flex-direction: column; align-items: center;
}
.hero-aura {
  position: absolute; top: 10%; left: 50%; transform: translateX(-50%);
  width: 500px; height: 400px; border-radius: 50%;
  background: radial-gradient(ellipse at center, rgba(47,101,255,0.06) 0%, transparent 60%);
  pointer-events: none;
}
.hero-line {
  width: 1px; height: 80px; background: linear-gradient(to bottom, transparent, #30363D, transparent);
  margin-bottom: 32px;
}
.hero-mark { font-size: 64px; display: block; margin-bottom: 20px; filter: drop-shadow(0 0 24px rgba(47,101,255,0.15)); }
.hero-text { margin-bottom: 16px; }
.hero h1 {
  font-size: 40px; font-weight: 200; color: #F0F6FC;
  letter-spacing: 0.25em; margin: 0;
  font-family: "PingFang SC","Noto Serif SC","SimSun",serif;
}
.hero-sub { font-size: 15px; color: #484F58; margin: 8px 0 0; letter-spacing: 0.1em; }
.hero-desc { font-size: 14px; color: #484F58; margin: 0 0 32px; line-height: 1.8; }
.hero-btn {
  cursor: pointer; border-radius: 14px;
  border: none; display: flex; align-items: center; justify-content: center;
  position: relative; transition: all 0.3s ease;
  padding: 10px 28px; font-family: inherit; font-size: 18px; font-weight: 600;
  color: #F0F6FC; background: transparent;
  box-shadow: 0 0.5px 0.5px 1px rgba(255,255,255,0.08),
    0 10px 20px rgba(0,0,0,0.3), 0 4px 5px 0px rgba(0,0,0,0.1);
}
.hero-btn:hover {
  transform: scale(1.02);
  box-shadow: 0 0 1px 2px rgba(255,255,255,0.12),
    0 15px 30px rgba(0,0,0,0.4), 0 10px 3px -3px rgba(0,0,0,0.1);
}
.hero-btn:active {
  transform: scale(1);
  box-shadow: 0 0 1px 2px rgba(255,255,255,0.08),
    0 10px 3px -3px rgba(0,0,0,0.2);
}

/* State content */
.btn-state {
  z-index: 2; display: flex; align-items: center; position: relative; gap: 10px;
}
.btn-icon {
  display: flex; align-items: center; justify-content: center; color: #8B949E;
  transform: scale(1.25); transition: all 0.3s ease;
}
.btn-icon svg { overflow: visible; }
.btn-state .btn-icon svg { animation: btn-land 0.6s ease forwards; }
.hero-btn:hover .btn-icon { transform: rotate(45deg) scale(1.25); }
@keyframes btn-land {
  0% { transform: translateX(-60px) translateY(30px) rotate(-50deg) scale(2); opacity: 0; filter: blur(3px); }
  100% { transform: translateX(0) translateY(0) rotate(0); opacity: 1; filter: blur(0); }
}

/* Character animation */
.btn-state p span {
  display: inline-block; opacity: 0;
  animation: btn-slideDown 0.8s ease forwards calc(var(--i) * 0.03s);
}
.hero-btn:hover .btn-state p span {
  animation: btn-wave 0.5s ease forwards calc(var(--i) * 0.02s);
}
@keyframes btn-wave {
  30% { opacity: 1; transform: translateY(4px) rotate(0); }
  50% { opacity: 1; transform: translateY(-3px) rotate(0); color: #58A6FF; }
  100% { opacity: 1; transform: translateY(0) rotate(0); }
}
@keyframes btn-slideDown {
  0% { opacity: 0; transform: translateY(-20px) translateX(5px) rotate(-90deg); color: #58A6FF; filter: blur(5px); }
  30% { opacity: 1; transform: translateY(4px) rotate(0); filter: blur(0); }
  50% { opacity: 1; transform: translateY(-3px) rotate(0); }
  100% { opacity: 1; transform: translateY(0) rotate(0); }
}

/* ====== Sections ====== */
.section { margin-bottom: 56px; }
.sec-head { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
.sec-line { width: 24px; height: 1px; background: #30363D; flex-shrink: 0; }
.section h2 { font-size: 13px; color: #484F58; font-weight: 500; letter-spacing: 0.08em; margin: 0; text-transform: uppercase; }

/* ====== Cases ====== */
.case-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.case-card {
  background: #0D1117; border: 1px solid #21262D; border-radius: 4px;
  padding: 16px; cursor: pointer; transition: all 0.25s;
  display: flex; flex-direction: column; gap: 6px;
  opacity: 0; animation: fadeUp 0.6s cubic-bezier(0.22,1,0.36,1) forwards;
}
@keyframes fadeUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
.case-card:hover { border-color: #2F65FF; background: #161B22; }
.cc-no { font-size: 11px; color: #58A6FF; letter-spacing: 0.02em; }
.cc-title { font-size: 14px; color: #F0F6FC; font-weight: 500; line-height: 1.4; }
.cc-court { font-size: 12px; color: #8B949E; }
.cc-summary { font-size: 11px; color: #484F58; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

/* ====== Judges ====== */
.judge-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.judge-card {
  background: #0D1117; border: 1px solid #21262D; border-radius: 4px;
  padding: 20px 16px; cursor: pointer; transition: all 0.25s;
  display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center;
  opacity: 0; animation: fadeUp 0.6s cubic-bezier(0.22,1,0.36,1) forwards;
}
.judge-card:hover { border-color: #2F65FF; background: #161B22; }
.jc-icon { font-size: 32px; opacity: 0.3; }
.jc-name { font-size: 15px; color: #F0F6FC; font-weight: 500; }
.jc-court { font-size: 12px; color: #8B949E; }
.jc-stats { font-size: 11px; color: #484F58; }

.landing-footer { text-align: center; font-size: 11px; color: #21262D; padding: 30px 0; }
</style>

<style>
body { background: #0F0F0F !important; }
</style>
