<script setup lang="ts">
defineOptions({ name: 'CompareView' })
import { ref, computed, watch, onMounted, onActivated, onUnmounted } from "vue"
import { useRouter } from "vue-router"
import api from "@/api/client"
import { Plus, Delete, Search, Download, Switch, Star } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { useAuthStore } from "@/stores/auth"
import { useCompareBasketStore, type CaseItem as BasketCaseItem } from "@/stores/compareBasket"
import UpgradePrompt from "@/components/common/UpgradePrompt.vue"

const router = useRouter()
const auth = useAuthStore()
const basket = useCompareBasketStore()

interface CaseItem { id: number; case_no: string; title: string; court: string; case_category_2: string; judgment_date: string; full_text?: string; trial_procedure?: string; court_level?: string }
const cases = ref<CaseItem[]>([])
const result = ref<any>(null)
const loading = ref(false)

// 从对比篮同步案例（首次加载 + KeepAlive 重新激活）
// Compare 页面自己的 localStorage 持久化 key
// Compare 页面自己的 localStorage 持久化 key（按用户隔离）
function compareCasesKey(): string {
  return `lvjing_compare_cases_${auth.user?.id || "anon"}`
}

function loadCasesFromStorage(): CaseItem[] {
  try {
    const raw = localStorage.getItem(compareCasesKey())
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveCasesToStorage() {
  localStorage.setItem(compareCasesKey(), JSON.stringify(cases.value))
}

function syncFromBasket() {
  // 如果 basket 还没加载数据，不做同步（避免误清案例）
  if (basket.cases.length === 0) return

  const basketIds = new Set(basket.cases.map(c => c.id))
  // 保留上传案例（负ID），移除对比篮中已不存在的数据库案例
  cases.value = cases.value.filter(c => c.id < 0 || basketIds.has(c.id))
  // 添加对比篮中新增的案例
  const existingIds = new Set(cases.value.map(c => c.id))
  for (const bc of basket.cases) {
    if (!existingIds.has(bc.id)) {
      if (cases.value.length >= 5) break
      cases.value.push({ ...bc })
    }
  }
  saveCasesToStorage()
  if (cases.value.length < 2 && result.value) {
    result.value = null
  }
}

onMounted(() => {
  // 优先从 localStorage 恢复（包含上传案例的完整数据）
  const saved = loadCasesFromStorage()
  if (saved.length > 0) {
    cases.value = saved
  }

  // 等 basket 加载后同步数据库案例
  const stop = watch(() => basket.cases, (newCases) => {
    if (newCases.length > 0) {
      const existingIds = new Set(cases.value.map(c => c.id))
      let changed = false
      for (const bc of newCases) {
        if (!existingIds.has(bc.id) && cases.value.length < 5) {
          cases.value.push({ ...bc })
          changed = true
        }
      }
      if (changed) {
        saveCasesToStorage()
      }
      stop()
    }
  }, { deep: true })

  // 兼容：如果 basket 已有数据
  if (basket.cases.length > 0) {
    stop()
    const existingIds = new Set(cases.value.map(c => c.id))
    let changed = false
    for (const bc of basket.cases) {
      if (!existingIds.has(bc.id) && cases.value.length < 5) {
        cases.value.push({ ...bc })
        changed = true
      }
    }
    if (changed) {
      saveCasesToStorage()
    }
  }
})

onActivated(() => {
  syncFromBasket()
})

// 监听用户切换，重新加载该用户的对标数据
watch(() => auth.user?.id, (uid) => {
  if (uid) {
    const saved = loadCasesFromStorage()
    cases.value = saved.length > 0 ? saved : []
    result.value = null
    // 同步对比篮中该用户的案例
    syncFromBasket()
  }
})

// 案例搜索
const searchQuery = ref("")
const searchResults = ref<CaseItem[]>([])
const searching = ref(false)
const showDropdown = ref(false)
const searchContainerRef = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

async function handleFileUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const formData = new FormData()
  formData.append("file", file)
  try {
    const res = await api.post("/compare/extract", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    const data = res.data
    // 构造一个案例对象加入对比列表
    const newCase: CaseItem = {
      id: -(Date.now()),  // 负数ID标识为上传案例
      case_no: data.case_no || "（无案号）",
      title: data.title || file.name.replace(/\.txt$/i, ""),
      court: data.court || "（未知法院）",
      case_category_2: data.case_category_2 || "",
      judgment_date: data.judgment_date || "",
      trial_procedure: data.trial_procedure || "",
      court_level: data.court_level || "",
      full_text: data.full_text || "",
    }
    if (cases.value.length >= 5) { ElMessage.warning("最多对比5个案例"); return }
    cases.value.push(newCase)
    basket.addCase({ id: newCase.id, case_no: newCase.case_no, title: newCase.title, court: newCase.court, case_category_2: newCase.case_category_2, judgment_date: newCase.judgment_date })
    saveCasesToStorage()
    ElMessage.success("判决书已添加")
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "上传失败")
  } finally {
    input.value = ""  // 重置以允许重复上传同一文件
  }
}

function handleCompareClickOutside(e: MouseEvent) {
  if (searchContainerRef.value && !searchContainerRef.value.contains(e.target as Node)) {
    showDropdown.value = false
  }
}

onMounted(() => {
  document.addEventListener("click", handleCompareClickOutside)
})

onUnmounted(() => {
  document.removeEventListener("click", handleCompareClickOutside)
})
watch(searchQuery, async (val) => {
  if (!val.trim()) {
    searchResults.value = []
    showDropdown.value = false
    return
  }
  searching.value = true
  try {
    const res = await api.get("/compare/search", { params: { q: val.trim() } })
    searchResults.value = res.data.filter((c: CaseItem) => !cases.value.some(s => s.id === c.id))
    showDropdown.value = searchResults.value.length > 0
  } catch {
    searchResults.value = []
    showDropdown.value = false
  } finally {
    searching.value = false
  }
})

function onSearchFocus() {
  if (searchResults.value.length > 0) showDropdown.value = true
}

function onSearchBlur() {
  setTimeout(() => { showDropdown.value = false }, 200)
}

function addCase(c: CaseItem) {
  if (cases.value.length >= 5) { ElMessage.warning("最多对比5个案例"); return }
  cases.value.push(c)
  basket.addCase(c)
  saveCasesToStorage()
  searchQuery.value = ""
  searchResults.value = []
  showDropdown.value = false
}

function removeCase(idx: number) {
  const removed = cases.value[idx]
  if (removed) basket.removeCase(removed.id)
  cases.value.splice(idx, 1)
  saveCasesToStorage()
  if (cases.value.length < 2) {
    result.value = null  // 不足2个案例，清除对比结果
  }
  if (searchQuery.value.trim()) {
    const val = searchQuery.value
    searchQuery.value = ""
    searchQuery.value = val
  }
}

async function doCompare() {
  if (cases.value.length < 2) { ElMessage.warning("请至少选择2个案例"); return }
  loading.value = true
  try {
    const dbCases = cases.value.filter(c => c.id > 0)
    const uploadedCases = cases.value.filter(c => c.id < 0).map(c => ({
      title: c.title,
      case_no: c.case_no,
      court: c.court,
      court_level: c.court_level || "",
      trial_procedure: c.trial_procedure || "",
      case_category_2: c.case_category_2,
      judgment_date: c.judgment_date,
      full_text: c.full_text || "",
    }))
    const res = await api.post("/compare/start", {
      case_ids: dbCases.map(c => c.id),
      uploaded_cases: uploadedCases,
    })
    result.value = res.data
  } catch (e: any) {
    const resp = e?.response
    if (!resp) {
      ElMessage.error("网络错误：无法连接后端")
    } else {
      const detail = resp.data?.detail
      const msg = Array.isArray(detail)
        ? detail.map((d: any) => d.msg || JSON.stringify(d)).join("；")
        : (typeof detail === "string" ? detail : JSON.stringify(resp.data || e.message))
      ElMessage.error(`[${resp.status}] ${msg}`)
    }
  } finally {
    loading.value = false
  }
}

function clearAll() {
  cases.value = []
  basket.clearAll()
  saveCasesToStorage()
  result.value = null
  searchQuery.value = ""
  searchResults.value = []
  showDropdown.value = false
}

async function exportResult() {
  if (!result.value) return
  if (cases.value.length < 2) { ElMessage.warning("至少需要2个案例才能导出对比报告"); return }
  try {
    const dbCases = cases.value.filter(c => c.id > 0)
    const uploadedCases = cases.value.filter(c => c.id < 0).map(c => ({
      title: c.title,
      case_no: c.case_no,
      court: c.court,
      court_level: c.court_level || "",
      trial_procedure: c.trial_procedure || "",
      case_category_2: c.case_category_2,
      judgment_date: c.judgment_date,
      full_text: c.full_text || "",
    }))
    const res = await api.post("/workspace/export/comparison", {
      case_ids: dbCases.map(c => c.id),
      uploaded_cases: uploadedCases,
    }, {
      responseType: "blob",
    })
    const blob = new Blob([res.data], { type: "text/plain;charset=utf-8" })
    const a = document.createElement("a")
    a.href = URL.createObjectURL(blob)
    a.download = `律镜_对标分析报告_${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success("对比报告已导出")
    // 刷新用户信息以更新导出计数
    await auth.fetchProfile()
  } catch (e: any) {
    if (e.response?.status === 402) {
      ElMessage.warning("导出次数已用完，请升级会员")
      showUpgrade.value = true
    } else {
      ElMessage.error("导出失败")
    }
  }
}

const canCompare = computed(() => cases.value.length >= 2)
const showUpgrade = ref(false)
</script>

<template>
  <div style="max-width: 1200px; margin: 0 auto">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0">
      <div>
        <h3 style="color:var(--text-primary);display:flex;align-items:center;gap:8px">
          案例对标分析
          <el-tag v-if="result?.is_premium" type="warning" size="small" effect="light">
            <el-icon><Star /></el-icon> 会员深度版
          </el-tag>
          <el-tag v-else-if="result" size="small" effect="plain">基础版</el-tag>
        </h3>
        <p style="color:var(--text-tertiary);font-size:13px;margin-top:4px">
          选择 2-5 个案例，自动对比关键维度并识别差异
          <template v-if="result && !result.is_premium">
            · <router-link to="/pricing" style="color:var(--accent-gold)">升级会员</router-link> 获取深度分析
          </template>
        </p>
      </div>
      <div style="display:flex;gap:8px">
        <button v-if="result" class="compare-btn gray" @click="exportResult">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
          <span>导出报告<template v-if="!auth.isPremium">（{{ auth.exportRemaining }}/2）</template></span>
        </button>
        <input
          ref="fileInput"
          type="file"
          accept=".txt"
          style="display:none"
          @change="handleFileUpload"
        />
        <button class="compare-btn gray" @click="fileInput?.click()" :disabled="cases.length >= 5">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="17 8 12 3 7 8"></polyline>
            <line x1="12" y1="3" x2="12" y2="15"></line>
          </svg>
          <span>上传判决书</span>
        </button>
        <button v-if="cases.length" class="compare-btn gray" @click="clearAll">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          <span>清空全部</span>
        </button>
      </div>
    </div>

    <!-- 搜索添加 -->
    <div v-if="cases.length < 5" style="display:flex;gap:8px;align-items:stretch;margin-top:4px;margin-bottom:16px">
        <div style="position:relative;flex:1" ref="searchContainerRef">
          <div class="search-box">
            <div class="search-icon-box">
              <svg viewBox="0 0 20 20" aria-hidden="true" class="search-svg" width="20" height="20">
                <path d="M16.72 17.78a.75.75 0 1 0 1.06-1.06l-1.06 1.06ZM9 14.5A5.5 5.5 0 0 1 3.5 9H2a7 7 0 0 0 7 7v-1.5ZM3.5 9A5.5 5.5 0 0 1 9 3.5V2a7 7 0 0 0-7 7h1.5ZM9 3.5A5.5 5.5 0 0 1 14.5 9H16a7 7 0 0 0-7-7v1.5Zm3.89 10.45 3.83 3.83 1.06-1.06-3.83-3.83-1.06 1.06ZM14.5 9a5.48 5.48 0 0 1-1.61 3.89l1.06 1.06A6.98 6.98 0 0 0 16 9h-1.5Zm-1.61 3.89A5.48 5.48 0 0 1 9 14.5V16a6.98 6.98 0 0 0 4.95-2.05l-1.06-1.06Z"></path>
              </svg>
            </div>
            <input
              type="text"
              class="search-input"
              v-model="searchQuery"
              placeholder="输入案号、案例名称或案由搜索..."
              @focus="onSearchFocus"
              @blur="onSearchBlur"
            />
          </div>

        <!-- 搜索结果下拉 -->
        <div v-if="showDropdown && searchResults.length" class="search-dropdown">
          <div
            v-for="c in searchResults" :key="c.id"
            class="search-item"
            @click="addCase(c)"
          >
            <div style="flex:1;min-width:0">
              <div style="color:var(--accent-blue);font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ c.title }}</div>
              <div style="color:var(--text-tertiary);font-size:11px">{{ c.case_no }} · {{ c.court }} · {{ c.case_category_2 }}</div>
            </div>
            <el-button size="small" :icon="Plus">添加</el-button>
          </div>
        </div>
      </div>
      <button
        class="compare-btn"
        :disabled="!canCompare || loading"
        @click="doCompare"
        :title="cases.length >= 2 ? `对比 ${cases.length} 个案例` : '请添加至少 2 个案例'"
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="4" y1="6" x2="16" y2="6"></line>
          <line x1="4" y1="12" x2="16" y2="12"></line>
          <line x1="4" y1="18" x2="12" y2="18"></line>
          <line x1="18" y1="8" x2="18" y2="16"></line>
          <polyline points="15 13 18 16 21 13"></polyline>
        </svg>
        <span>{{ loading ? '分析中...' : '对比' }}</span>
      </button>
    </div>

    <!-- 案例选择区 -->
    <el-card v-if="cases.length" shadow="never" style="margin-top:16px;margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <!-- 已选案例标签 -->
        <el-tag
          v-for="(c, i) in cases" :key="c.id"
          closable size="large"
          @close="removeCase(i)"
          class="case-tag"
          @click="c.id > 0 && router.push('/case/' + c.id)"
          :style="c.id < 0 ? { cursor: 'default' } : {}"
        >
          <span style="font-weight:600">{{ c.title }}</span>
          <span style="color:var(--text-tertiary);margin-left:6px;font-size:11px">{{ c.case_no }}</span>
        </el-tag>
      </div>
    </el-card>

    <!-- 对比结果 — 卡片视图 -->
    <div v-if="result && cases.length">
      <!-- 案例概览卡片 -->
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px">
        <el-card v-for="(c, i) in cases" :key="c.id" shadow="hover" class="overview-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div style="flex:1;min-width:0;cursor:pointer" @click="router.push('/case/' + c.id)">
              <div style="color:var(--accent-blue);font-weight:600;font-size:14px;margin-bottom:4px">{{ c.title }}</div>
              <div style="font-size:11px;color:var(--text-tertiary)">{{ c.case_no }}</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:4px">{{ c.court }}</div>
              <div style="font-size:11px;color:var(--text-muted)">{{ c.case_category_2 }}</div>
            </div>
            <el-button size="small" text type="danger" :icon="Delete" @click="removeCase(i)" style="flex-shrink:0" />
          </div>
        </el-card>
      </div>

      <!-- 对比矩阵 -->
      <el-card shadow="never" style="margin-bottom:16px">
        <h4 style="margin-bottom:12px;color:var(--text-primary)">对比矩阵</h4>
        <div style="overflow-x:auto">
          <table class="compare-table">
            <thead>
              <tr>
                <th style="min-width:100px">对比维度</th>
                <th v-for="(c, i) in cases" :key="i" style="min-width:160px" :title="result.matrix?.[1]?.values?.[i] || c.title">
                  {{ (result.matrix?.[1]?.values?.[i] || c.title || '案例' + (i+1)).slice(0, 14) }}{{ (result.matrix?.[1]?.values?.[i] || c.title || '').length > 14 ? '…' : '' }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in result.matrix" :key="row.dimension">
                <td class="dim-label">{{ row.dimension }}</td>
                <td v-for="(v, j) in row.values" :key="j"
                  :style="{ background: Number(j) > 0 && row.values[j] !== row.values[0] ? 'rgba(240,192,64,0.15)' : '' }"
                >
                  {{ v }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p style="color:var(--text-tertiary);font-size:11px;margin-top:8px">🟡 高亮 = 与{{ cases[0]?.title?.slice(0, 16) || '首个案例' }}不同</p>
      </el-card>

      <!-- 关键差异变量 -->
      <el-card shadow="never">
        <h4 style="margin-bottom:12px;color:var(--text-primary)">关键差异变量</h4>
        <div v-if="result.key_variables?.length">
          <div v-for="(v, i) in result.key_variables" :key="i" class="kv-item">
            <div class="kv-icon">💡</div>
            <div style="flex:1">
              <p class="kv-desc">{{ v.description }}</p>
              <div class="kv-refs">
                <span v-for="ref in v.evidence_refs" :key="ref" class="kv-ref">{{ ref }}</span>
              </div>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂未识别出关键差异变量" :image-size="60" />
      </el-card>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="!cases.length && !loading" description="搜索并添加案例开始对标分析">
      <p style="color:var(--text-tertiary);font-size:13px">输入案号或案例名称搜索，选择 2-5 个案例进行对比</p>
    </el-empty>

    <!-- 升级引导 -->
    <UpgradePrompt
      v-model:visible="showUpgrade"
      feature-name="案例报告导出"
      description="免费用户只能导出2次报告，升级会员即可无限导出。"
    />
  </div>
</template>

<style scoped>
.case-tag {
  cursor: pointer; user-select: none; padding: 7px 14px;
  border-radius: 20px !important;
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}
.case-tag:hover { opacity: 0.85; transform: scale(1.03); }
.search-dropdown {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 50;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border: none; border-radius: 14px;
  box-shadow: 0 0 0 1px rgba(0,0,0,0.06), 0 8px 32px rgba(0,0,0,0.10);
  max-height: 320px; overflow-y: auto;
}
.search-item {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; cursor: pointer; transition: background 0.15s;
  color: var(--text-secondary);
}
.search-item:hover { background: var(--bg-hover); }
.overview-card {
  transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1);
  border: none !important;
  border-radius: var(--radius-lg) !important;
  box-shadow: 0 0 0 1px var(--ring-color) !important;
}
.overview-card:hover {
  box-shadow: 0 4px 20px rgba(26, 39, 68, 0.06), 0 0 0 1px var(--ring-color-strong) !important;
  transform: translateY(-2px);
}
.compare-table {
  width: 100%; border-collapse: collapse; font-size: 13px; color: var(--text-secondary);
  border-radius: var(--radius-md); overflow: hidden;
}
.compare-table th, .compare-table td { padding: 12px 14px; border: 1px solid var(--ring-color); text-align: left; }
.compare-table th { background: var(--bg-tertiary); font-weight: 600; color: var(--text-primary); font-size: 12px; }
.dim-label { font-weight: 600; color: var(--text-secondary); background: var(--bg-tertiary); white-space: nowrap; }
.kv-item {
  display: flex; gap: 12px; padding: 14px; background: rgba(240, 192, 64, 0.06);
  border-radius: 14px; margin-bottom: 8px; border: none !important;
  box-shadow: 0 0 0 1px rgba(240, 192, 64, 0.20);
  transition: background 0.2s;
}
.kv-item:hover { background: rgba(240, 192, 64, 0.10); }
.kv-icon { font-size: 20px; flex-shrink: 0; }
.kv-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; }
.kv-refs { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 8px; }
.kv-ref { font-size: 11px; color: var(--text-tertiary); background: var(--bg-input); padding: 3px 10px; border-radius: 6px; }

.compare-btn {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 0 14px; cursor: pointer; font-weight: 600; font-size: 13px;
  border-radius: 8px; border: none; font-family: inherit; flex-shrink: 0;
  background: #2F65FF; color: #F0F6FC; transition: background 0.2s;
}
.compare-btn:hover { background: #58A6FF; }
.compare-btn svg { width: 15px; flex-shrink: 0; }
.compare-btn:disabled { opacity: 0.35; cursor: not-allowed; }

/* 去掉卡片背景和边框 */
:deep(.el-card) { background: transparent !important; box-shadow: none !important; }

/* 灰色变体 */
.compare-btn.gray {
  text-shadow: 2px 2px 3px rgba(100,100,100,0.2);
  background: linear-gradient(15deg, #484F58, #30363D, #21262D, #161B22, #484F58, #30363D, #21262D, #161B22) no-repeat;
  background-size: 300%; background-position: left center;
  border-radius: 8px; box-shadow: 0 20px 10px -20px rgba(0,0,0,0.3); color: #8B949E; font-size: 13px; padding: 0.9em 1rem;
}
.compare-btn.gray:hover { background-size: 320%; background-position: right center; color: #F0F6FC; }
.compare-btn.gray svg { fill: #8B949E; width: 18px; }
.compare-btn.gray:hover svg { fill: #F0F6FC; }

/* 搜索输入框 */
.search-box {
  display: flex; height: 44px; border-radius: 8px; overflow: hidden;
  box-shadow: 0 0 0 1px #30363D;
}
.search-icon-box {
  display: flex; width: 44px; align-items: center; justify-content: center;
  background: #0D1117; border-right: 1px solid #30363D; flex-shrink: 0;
  border-radius: 8px 0 0 8px;
}
.search-svg { fill: #484F58; }
.search-input {
  flex: 1; background: #0D1117; border: none; outline: none;
  color: #F0F6FC; font-size: 14px; font-family: inherit; padding: 0 12px;
  border-radius: 0 8px 8px 0;
}
.search-input::placeholder { color: #484F58; }
</style>
