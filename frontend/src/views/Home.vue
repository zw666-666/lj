<script setup lang="ts">
defineOptions({ name: 'HomeView' })
import { ref, reactive, computed, onMounted, onUnmounted, watch } from "vue"
import { useRouter } from "vue-router"
import api from "@/api/client"
import { useSearchStore } from "@/stores/search"
import { useAuthStore } from "@/stores/auth"
import { useCompareBasketStore } from "@/stores/compareBasket"
import {
  Search, Document, Delete, Clock, Filter, Refresh, Upload, Loading, Plus, Switch, Close
} from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"

const router = useRouter()
const auth = useAuthStore()
const basket = useCompareBasketStore()
const searchStore = useSearchStore()

function toggleCompare(c: any, ev: Event) {
  ev.stopPropagation()
  if (basket.hasCase(c.id)) { basket.removeCase(c.id); ElMessage.success("已移出对比") }
  else { if (basket.addCase(c)) { ElMessage.success("已加入对比") } else { ElMessage.warning("对比篮已满（最多5个案例）") } }
}

const searchMode = ref<"semantic" | "structured" | "case_to_case">("semantic")
const query = ref("")
const loading = ref(false)
const structFields = reactive({ cause: "", court_level: "", procedure: "", region: "", date_from: "", date_to: "", article: "" })
const sortBy = ref("relevance")
const results = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const fallback = ref("")
const searchError = ref("")
const uploadedFileName = ref("")
const uploadingFile = ref(false)
const searchHistory = ref<string[]>([])
const showHistory = ref(false)
const showFilters = ref(false)
const historyKey = computed(() => `lvjing_search_history_${auth.user?.id || "anon"}`)

function handleClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest(".search-bar")) { showHistory.value = false }
}

async function loadSearchHistory() {
  try {
    const res = await api.get("/workspace/search-history")
    searchHistory.value = res.data.map((item: any) => item.detail).filter(Boolean)
  } catch {
    const saved = localStorage.getItem(historyKey.value)
    if (saved) searchHistory.value = JSON.parse(saved)
  }
}

watch(() => auth.user?.id, (uid) => { if (uid) loadSearchHistory() })
watch(() => searchStore.refreshFlag, () => { if (results.value.length > 0) doSearch() })

onMounted(() => {
  if (auth.user?.id) loadSearchHistory()
  document.addEventListener("click", handleClickOutside)
})
onUnmounted(() => { document.removeEventListener("click", handleClickOutside) })

function saveHistory(q: string) {
  if (!q.trim()) return
  const idx = searchHistory.value.indexOf(q)
  if (idx > -1) searchHistory.value.splice(idx, 1)
  searchHistory.value.unshift(q)
  if (searchHistory.value.length > 20) searchHistory.value.pop()
  localStorage.setItem(historyKey.value, JSON.stringify(searchHistory.value))
}
function clearHistory() { searchHistory.value = []; localStorage.removeItem(historyKey.value) }
function removeHistoryItem(h: string) { searchHistory.value = searchHistory.value.filter(s => s !== h); localStorage.setItem(historyKey.value, JSON.stringify(searchHistory.value)) }

async function doSearch(p?: number) {
  const q = query.value.trim()
  if (!q && searchMode.value !== "structured") { results.value = []; total.value = 0; return }
  if (q) saveHistory(q)
  showHistory.value = false; loading.value = true; page.value = p || 1
  try {
    const body: any = { query: q, mode: searchMode.value, page: page.value, page_size: pageSize.value, sort_by: sortBy.value }
    if (searchMode.value === "structured") {
      if (structFields.cause) body.cause = [structFields.cause]
      if (structFields.court_level) body.court_level = structFields.court_level
      if (structFields.procedure) body.procedure = structFields.procedure
      if (structFields.region) body.region = structFields.region
      if (structFields.date_from) body.date_from = structFields.date_from
      if (structFields.date_to) body.date_to = structFields.date_to
      if (structFields.article) body.article = structFields.article
    }
    const res = await api.post("/search/semantic", body)
    results.value = res.data.results; total.value = res.data.total
    fallback.value = res.data.fallback_note || ""; searchError.value = ""
    const lvl: Record<string, string> = { supreme: "最高人民法院", high: "高级人民法院", intermediate: "中级人民法院", basic: "基层人民法院" }
    const proc: Record<string, string> = { first: "一审", second: "二审", retrial: "再审", supervision: "审判监督" }
    if (searchMode.value === "structured") {
      const parts: string[] = []
      if (structFields.cause) parts.push(structFields.cause)
      if (structFields.court_level) parts.push(lvl[structFields.court_level] || structFields.court_level)
      if (structFields.procedure) parts.push(proc[structFields.procedure] || structFields.procedure)
      if (q.trim()) parts.push(q.trim())
      searchStore.setQuery(parts.join(" "))
    } else if (searchMode.value === "case_to_case") { searchStore.setQuery(q.trim().slice(0, 100)) }
    else { searchStore.setQuery(q.trim()) }
  } catch (e: any) {
    results.value = []; total.value = 0
    const status = e?.response?.status
    if (!status) searchError.value = "网络连接失败，请确认后端已启动（http://127.0.0.1:8000）"
    else if (status === 500) searchError.value = "服务器内部错误，请查看后端终端日志"
    else searchError.value = `请求失败 (${status})：${e?.response?.data?.detail || e?.message || "未知错误"}`
  } finally { loading.value = false }
}

function useHistoryItem(h: string) { query.value = h; showHistory.value = false; doSearch() }

function handleFileUpload(file: any) {
  uploadingFile.value = true
  const reader = new FileReader()
  reader.onload = (e) => {
    const text = e.target?.result as string
    if (text) { query.value = text; uploadedFileName.value = file.name; doSearch() }
    uploadingFile.value = false
  }
  reader.onerror = () => { uploadingFile.value = false; searchError.value = "文件读取失败" }
  reader.readAsText(file, "UTF-8")
  return false
}
function clearFileUpload() { query.value = ""; uploadedFileName.value = ""; searchError.value = "" }
function goToCase(id: number) { router.push(`/case/${id}`) }

const modeTips: Record<string, string> = {
  semantic: "用自然语言描述案情，系统自动理解并检索相关案例",
  structured: "按案由、法院层级、审判程序等条件精确组合检索",
  case_to_case: "上传或粘贴一份判决书全文，检索最相似案例",
}
const procedureLabels: Record<string, string> = { first: "一审", second: "二审", retrial: "再审", supervision: "审判监督" }
const courtLevelLabels: Record<string, string> = { supreme: "最高人民法院", high: "高级人民法院", intermediate: "中级人民法院", basic: "基层人民法院" }
const causeOptions = [
  { label: "民事 - 合同纠纷 - 买卖合同", value: "买卖合同纠纷" },
  { label: "民事 - 合同纠纷 - 建设工程合同", value: "建设工程合同纠纷" },
  { label: "民事 - 合同纠纷 - 借款合同", value: "借款合同纠纷" },
  { label: "民事 - 侵权 - 机动车交通事故", value: "机动车交通事故责任纠纷" },
  { label: "民事 - 知识产权 - 著作权", value: "著作权权属侵权纠纷" },
  { label: "民事 - 劳动争议", value: "劳动争议" },
  { label: "行政 - 行政处罚", value: "行政处罚" },
  { label: "刑事 - 经济犯罪", value: "经济犯罪" },
]
const courtLevels = [
  { label: "最高人民法院", value: "supreme" }, { label: "高级人民法院", value: "high" },
  { label: "中级人民法院", value: "intermediate" }, { label: "基层人民法院", value: "basic" },
]
const procedures = [
  { label: "一审", value: "first" }, { label: "二审", value: "second" },
  { label: "再审", value: "retrial" }, { label: "审判监督", value: "supervision" },
]
</script>

<template>
<div class="search-page">
    <div class="search-hero" :class="{ compact: results.length > 0 }">
      <div class="search-bar">
        <template v-if="searchMode === 'semantic'">
          <div class="glow-input-wrap" @click="showHistory = true">
            <div class="glow-layer glow-nebula"></div>
            <div class="glow-layer glow-dark1"></div>
            <div class="glow-layer glow-dark2"></div>
            <div class="glow-layer glow-dark3"></div>
            <div class="glow-layer glow-stardust"></div>
            <div class="glow-layer glow-ring"></div>
            <div class="glow-inner" :class="{ 'has-content': query.trim() }">
              <input v-model="query" placeholder="搜索案件......" @keyup.enter="doSearch()" @focus="showHistory = true" />
              <div class="input-mask-bar"></div>
              <div class="pink-glow-dot"></div>
              <div class="filter-icon-wrap">
                <div class="filter-border-rot"></div>
                <button class="filter-icon-btn" :disabled="loading" @click.stop="doSearch()">
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#d6d6e6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="22" y1="22" x2="16.65" y2="16.65"/></svg>
                </button>
              </div>
            </div>
          </div>
          <div v-if="showHistory && searchHistory.length" class="history-dropdown" @mousedown.prevent>
            <div class="history-header"><span><el-icon><Clock /></el-icon> 搜索历史</span><el-button link type="danger" size="small" @click="clearHistory">清空</el-button></div>
            <div v-for="h in searchHistory" :key="h" class="history-item" @click="useHistoryItem(h)"><el-icon><Clock /></el-icon><span class="hi-text">{{ h }}</span><el-icon class="hi-del" @click.stop="removeHistoryItem(h)"><Close /></el-icon></div>
          </div>
        </template>
        <template v-else-if="searchMode === 'structured'">
          <div class="struct-fields">
            <el-input v-model="query" placeholder="关键词（可选）" clearable style="width:200px" />
            <el-select v-model="structFields.cause" placeholder="案由" clearable filterable style="width:220px"><el-option v-for="c in causeOptions" :key="c.value" :label="c.label" :value="c.value" /></el-select>
            <el-select v-model="structFields.court_level" placeholder="法院层级" clearable style="width:150px"><el-option v-for="c in courtLevels" :key="c.value" :label="c.label" :value="c.value" /></el-select>
            <el-select v-model="structFields.procedure" placeholder="审判程序" clearable style="width:120px"><el-option v-for="p in procedures" :key="p.value" :label="p.label" :value="p.value" /></el-select>
            <el-input v-model="structFields.region" placeholder="地域" clearable style="width:120px" />
            <el-date-picker v-model="structFields.date_from" type="date" placeholder="开始日期" value-format="YYYY-MM-DD" style="width:140px" />
            <el-date-picker v-model="structFields.date_to" type="date" placeholder="结束日期" value-format="YYYY-MM-DD" style="width:140px" />
            <button class="compare-btn" :disabled="loading" @click="doSearch()"><svg viewBox="0 0 36 24" xmlns="http://www.w3.org/2000/svg"><path d="m18 0 8 12 10-8-4 20H4L0 4l10 8 8-12z"/></svg><span>检索</span></button>
            <button class="compare-btn gray" @click="Object.assign(structFields,{cause:'',court_level:'',procedure:'',region:'',date_from:'',date_to:'',article:''}); query=''"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg><span>重置</span></button>
          </div>
        </template>
        <template v-else>
          <div class="case-to-case">
            <div v-if="uploadedFileName" style="margin-bottom:10px;display:flex;align-items:center;gap:8px">
              <el-tag type="success" closable @close="clearFileUpload"><el-icon style="margin-right:4px"><Upload /></el-icon>{{ uploadedFileName }}</el-tag>
              <span style="font-size:12px;color:#8B949E">文件内容已加载，可修改后重新检索</span>
            </div>
            <el-input v-model="query" type="textarea" :rows="3" placeholder="在此粘贴判决书全文（或关键段落），系统自动检索最相似案例" />
            <div class="case-actions">
              <button class="compare-btn" :disabled="!query.trim()||uploadingFile||loading" @click="doSearch()"><svg viewBox="0 0 36 24" xmlns="http://www.w3.org/2000/svg"><path d="m18 0 8 12 10-8-4 20H4L0 4l10 8 8-12z"/></svg><span>{{ loading?'检索中...':'以案搜案' }}</span></button>
              <el-upload :show-file-list="false" accept=".txt,.doc,.docx" :before-upload="handleFileUpload" :disabled="uploadingFile"><button class="compare-btn gray" :disabled="uploadingFile"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg><span>{{ uploadingFile?'读取中...':'上传文件' }}</span></button></el-upload>
              <button v-if="query" class="compare-btn gray" @click="clearFileUpload"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg><span>清空</span></button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <div class="mode-switch">
      <p class="mode-tip">{{ modeTips[searchMode] }}</p>
      <div class="mode-tabs">
        <button v-for="m in ['semantic','structured','case_to_case']" :key="m" class="mode-btn" :class="{active:searchMode===m}" @click="searchMode=m as any">{{ m==='semantic'?'语义检索':m==='structured'?'结构化检索':'以案搜案' }}</button>
      </div>
    </div>

    <div v-if="results.length||loading" class="results-area">
      <div v-if="total>0" class="results-header">
        <div class="results-count">共<b>{{ total }}</b> 条结果<el-select v-model="sortBy" size="small" style="width:140px;margin-left:16px" @change="doSearch()"><el-option label="相关度排序" value="relevance"/><el-option label="最新日期" value="date"/><el-option label="法院层级" value="court_level"/><el-option label="审判程序" value="procedure"/></el-select></div>
        <div style="display:flex;align-items:center;gap:12px">
          <el-badge :value="basket.count" :hidden="basket.count===0" type="primary"><el-button size="small" :icon="Switch" @click="router.push('/compare')" :type="basket.count>0?'primary':'default'">对比篮</el-button></el-badge>
          <el-button text :icon="Filter" size="small" @click="showFilters=!showFilters">{{ showFilters?'收起筛选':'展开筛选' }}</el-button>
        </div>
      </div>
      <div v-if="showFilters&&total>0" class="filter-panel">
        <el-row :gutter="12"><el-col :span="6"><el-select v-model="structFields.cause" placeholder="案由" clearable size="small" style="width:100%"><el-option v-for="c in causeOptions" :key="c.value" :label="c.label" :value="c.value"/></el-select></el-col><el-col :span="4"><el-select v-model="structFields.court_level" placeholder="法院层级" clearable size="small" style="width:100%"><el-option v-for="c in courtLevels" :key="c.value" :label="c.label" :value="c.value"/></el-select></el-col><el-col :span="4"><el-select v-model="structFields.procedure" placeholder="审判程序" clearable size="small" style="width:100%"><el-option v-for="p in procedures" :key="p.value" :label="p.label" :value="p.value"/></el-select></el-col><el-col :span="4"><el-input v-model="structFields.region" placeholder="地域" clearable size="small"/></el-col><el-col :span="6"><el-button type="primary" size="small" @click="doSearch()">应用筛选</el-button><el-button size="small" @click="structFields.cause='';structFields.court_level='';structFields.procedure='';structFields.region='';doSearch()">清除</el-button></el-col></el-row>
      </div>
      <el-alert v-if="!loading&&searchError" :title="searchError" type="error" show-icon style="margin-bottom:16px"/>
      <div v-if="loading" style="text-align:center;padding:60px"><el-icon class="is-loading" :size="36" color="#58A6FF"><Loading /></el-icon><p style="color:#8B949E;margin-top:12px">正在检索案例库...</p></div>
      <el-alert v-if="!loading&&fallback" :title="fallback" type="info" show-icon style="margin-bottom:20px"/>
      <div v-if="!loading" class="result-cards">
        <el-card v-for="item in results" :key="item.id" shadow="hover" class="result-card" @click="goToCase(item.id)">
          <div class="card-main">
            <div class="card-info"><h4 class="card-title">{{ item.title||item.case_no }}</h4><p class="card-summary">{{ item.ai_summary||'暂无AI摘要，点击查看详情' }}</p><div class="card-meta"><el-tag size="small" type="info">{{ item.case_no }}</el-tag><span class="meta-sep">|</span><span>{{ item.court }}</span><span class="meta-sep">|</span><span>{{ procedureLabels[item.trial_procedure]||item.trial_procedure }}</span><span class="meta-sep">|</span><span>{{ item.judgment_date }}</span></div><el-tag v-if="item.matched_focus" size="small" type="warning" effect="plain" style="margin-top:6px">{{ item.matched_focus }}</el-tag></div>
            <div class="card-score"><div class="score-circle" :style="{'--pct':(item.relevance_score*100).toFixed(0)}">{{ (item.relevance_score*100).toFixed(0) }}%</div><span class="score-label">相关度</span></div>
          </div>
          <div class="card-compare" @click.stop>
            <el-button v-if="!basket.hasCase(item.id)" size="small" :icon="Plus" type="primary" plain @click="toggleCompare(item,$event)">加入对比</el-button>
            <el-tag v-else size="small" type="success" closable @close="basket.removeCase(item.id)">已加入对比</el-tag>
          </div>
        </el-card>
      </div>
      <div v-if="!loading && total > pageSize" class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next, jumper"
          background
          @current-change="doSearch(page)"
        />
      </div>
    </div>

    <div v-if="!results.length&&!loading" class="empty-state">
      <div class="empty-glow"></div>
      <span class="empty-icon">&#x2696;</span>
      <h3>以数为镜，洞察裁判之律</h3>
      <p>输入案情关键词，AI 从海量裁判文书中为您检索最相关案例</p>
    </div>

  </div>
</template>

<style scoped>
.search-page { max-width:1060px;margin:0 auto;padding:0 20px 60px;animation:fade-up 0.5s cubic-bezier(0.22,1,0.36,1) both; }
.search-hero { text-align:center;padding:48px 0 28px;transition:all 0.3s; }
.search-hero.compact { padding:14px 0 18px; }
.search-bar { position:relative;max-width:720px;margin:0 auto; }

.mode-switch { text-align:center;margin-bottom:8px; }
.mode-tip { color:#484F58;font-size:13px;margin-bottom:10px; }
.mode-tabs { display:flex;justify-content:center;gap:4px;margin-bottom:10px; }
.mode-btn { --color:#58A6FF;font-family:inherit;display:inline-block;width:auto;padding:0 22px;height:2.6em;line-height:2.5em;overflow:hidden;cursor:pointer;font-size:14px;z-index:1;color:var(--color);border:1.5px solid var(--color);border-radius:6px;position:relative;background:transparent;transition:color 0.3s;margin:0 4px; }
.mode-btn::before { position:absolute;content:"";background:var(--color);width:180px;height:220px;z-index:-1;border-radius:50%;top:100%;left:100%;transition:0.3s all; }
.mode-btn:hover { color:#fff; }
.mode-btn:hover::before { top:-40px;left:-40px; }
.mode-btn.active { color:#fff;border-color:#2F65FF; }
.mode-btn.active::before { top:-20px;left:-20px;background:#2F65FF; }

.struct-fields { display:flex;flex-wrap:wrap;gap:8px;justify-content:center;align-items:center; }
.case-to-case { text-align:left; }
.case-actions { display:flex;gap:8px;margin-top:12px;align-items:center; }

.history-dropdown { position:absolute;top:100%;left:0;right:0;background:#161B22;border:1px solid #30363D;border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,0.5);max-height:260px;overflow-y:auto;z-index:50;margin-top:6px; }
.history-header { display:flex;justify-content:space-between;align-items:center;padding:12px 16px;font-size:12px;color:#8B949E;border-bottom:1px solid #21262D; }
.history-item { display:flex;align-items:center;gap:8px;padding:10px 16px;font-size:13px;color:#8B949E;cursor:pointer;text-align:left; }
.history-item:hover { background:#21262D;color:#58A6FF; }
.hi-text { flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.hi-del { flex-shrink:0;opacity:0;transition:opacity 0.15s;color:#484F58; }
.history-item:hover .hi-del { opacity:1; }
.hi-del:hover { color:#F87171; }

.results-area { margin-top:12px; }
.results-header { display:flex;justify-content:space-between;align-items:center;margin-bottom:16px; }
.results-count { font-size:14px;color:#8B949E; }
.results-count b { color:#F0F6FC; }
.filter-panel { background:#161B22;border:1px solid #21262D;border-radius:14px;padding:16px;margin-bottom:16px; }
.result-cards { display:flex;flex-direction:column;gap:12px; }
.pagination-wrap { display:flex;justify-content:center;padding:24px 0 8px; }
.result-card { cursor:pointer;border-radius:14px;transition:all 0.25s; }
.result-card:hover { transform:translateY(-2px);box-shadow:0 0 0 1px rgba(47,101,255,0.25),0 6px 24px rgba(0,0,0,0.4)!important; }
.card-main { display:flex;justify-content:space-between;align-items:flex-start; }
.card-info { flex:1;min-width:0; }
.card-title { color:#58A6FF;font-size:15px;margin-bottom:4px;font-weight:600; }
.card-summary { color:#8B949E;font-size:13px;line-height:1.5;margin-bottom:8px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden; }
.card-meta { display:flex;align-items:center;gap:6px;font-size:12px;color:#484F58;flex-wrap:wrap; }
.meta-sep { color:#30363D; }
.card-score { text-align:center;min-width:64px; }
.card-compare { margin-top:10px;display:flex;justify-content:flex-end; }
.score-circle { width:52px;height:52px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;color:#58A6FF;background:conic-gradient(#58A6FF calc(var(--pct)*1%),#21262D 0);position:relative; }
.score-circle::after { content:'';position:absolute;width:40px;height:40px;background:#161B22;border-radius:50%; }
.score-label { font-size:11px;color:#8B949E;margin-top:4px;display:block; }
.empty-state { text-align:center;padding:100px 20px;color:#8B949E;position:relative; }
.empty-glow {
  position:absolute;top:50%;left:50%;transform:translate(-50%,-70%);
  width:140px;height:140px;border-radius:50%;
  background:radial-gradient(circle,rgba(47,101,255,0.10) 0%,transparent 70%);
  pointer-events:none;
}
.empty-icon { display:block;font-size:48px;color:#F0F6FC;margin-bottom:28px;filter:drop-shadow(0 0 12px rgba(47,101,255,0.15)); }
.empty-state h3 { font-size:26px;color:#F0F6FC;margin:0 0 10px;font-weight:200;letter-spacing:0.12em;font-family:"PingFang SC","Noto Serif SC","SimSun",serif; }
.empty-state p { font-size:13px;color:#484F58; }

.compare-btn { margin-top:0;display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:0.7em 1.2em;cursor:pointer;font-weight:700;font-size:14px;border-radius:30px;border:none;font-family:inherit;text-shadow:2px 2px 3px rgba(47,101,255,0.3);background:linear-gradient(15deg,#58A6FF,#2F65FF,#1F3A60,#161B22,#58A6FF,#2F65FF,#1F3A60,#161B22) no-repeat;background-size:300%;background-position:left center;color:#F0F6FC;box-shadow:0 20px 10px -20px rgba(47,101,255,0.15);transition:background 0.3s ease,color 0.3s ease; }
.compare-btn:hover { background-size:320%;background-position:right center;color:#fff; }
.compare-btn svg { width:18px;fill:#F0F6FC;transition:0.3s ease; }
.compare-btn:hover svg { fill:#fff; }
.compare-btn:disabled { opacity:0.85;cursor:not-allowed; }
.compare-btn.gray { text-shadow:2px 2px 3px rgba(100,100,100,0.2);background:linear-gradient(15deg,#484F58,#30363D,#21262D,#161B22,#484F58,#30363D,#21262D,#161B22) no-repeat;background-size:300%;background-position:left center;box-shadow:0 20px 10px -20px rgba(0,0,0,0.3);color:#8B949E;font-weight:600; }
.compare-btn.gray:hover { background-size:320%;background-position:right center;color:#F0F6FC; }
.compare-btn.gray svg { fill:#8B949E; }
.compare-btn.gray:hover svg { fill:#F0F6FC; }

</style>
