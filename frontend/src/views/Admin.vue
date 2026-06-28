<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue"
import api from "@/api/client"
import { ElMessage, ElMessageBox } from "element-plus"
import { Refresh, User, Plus, Upload, Delete } from "@element-plus/icons-vue"
import CountUp from "@/components/common/CountUp.vue"
import GridScan from "@/components/common/GridScan.vue"
import { useAuthStore } from "@/stores/auth"

const auth = useAuthStore()

const stats = ref<any>({})
const pendingCases = ref<any[]>([])
const totalPending = ref(0)
const loading = ref(false)

// 点击查看完整内容的弹窗
const detailVisible = ref(false)
const detailTitle = ref("")
const detailContent = ref("")

function showDetail(label: string, text: string) {
  if (!text) return
  detailTitle.value = label
  detailContent.value = text
  detailVisible.value = true
}

// 用户管理
const users = ref<any[]>([])
const showUsers = ref(false)

// ======================== 批量提交案例 ========================
interface BatchCase {
  uid: string        // 前端临时ID
  file_name: string
  case_no: string
  title: string
  court: string
  court_level: string
  court_region: string
  judge_name: string
  trial_procedure: string
  case_category_1: string
  case_category_2: string
  case_category_3: string
  judgment_date: string
  full_text: string
  summary: string
  ruling_abstract: string
}

const showSubmitDialog = ref(false)
const submitting = ref(false)
const uploadingFile = ref(false)
const batchCases = ref<BatchCase[]>([])
const batchUidCounter = ref(0)

function emptyBatchCase(): BatchCase {
  batchUidCounter.value++
  return {
    uid: `c_${batchUidCounter.value}`,
    file_name: "", case_no: "", title: "", court: "", court_level: "intermediate",
    court_region: "", judge_name: "", trial_procedure: "first",
    case_category_1: "", case_category_2: "", case_category_3: "",
    judgment_date: "", full_text: "", summary: "", ruling_abstract: "",
  }
}

/** 从判决书文本和文件名提取元数据 */
function extractMeta(text: string, fileName: string): Partial<BatchCase> {
  const result: Partial<BatchCase> = {}
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
  const head = lines.slice(0, 30).join('\n')  // 前30行搜索

  // 案号：匹配 (2024)京02民终007号 / (2019)最高法民终1001号 等
  const caseNoPatterns = [
    /[（(]\s*\d{4}\s*[）)]\s*[一-龥\d]{2,25}号/,
    /案\s*号[：:]\s*([（(]\d{4}[）)][一-龥\d]{2,20}号)/,
  ]
  for (const pat of caseNoPatterns) {
    const m = head.match(pat)
    if (m) { result.case_no = m[0].replace(/[（(]/g, '(').replace(/[）)]/g, ')').replace(/\s+/g, ''); break }
  }

  // 标题：优先从文件名提取（格式: NN_Title.txt）
  if (fileName) {
    const nameMatch = fileName.match(/^(?:\d+_)?(.+)\.\w+$/)
    if (nameMatch) {
      result.title = nameMatch[1]
    }
  }

  // 标题回退：从文本内容匹配
  if (!result.title) {
    const titlePatterns = [
      /([一-龥A-Za-z0-9·（）()]+)\s*诉\s*([一-龥A-Za-z0-9·（）()]+)\s*([一-龥]+?)\s*[纠案][纷件]/,
      /([一-龥A-Za-z0-9·（）()]+)\s*与\s*([一-龥A-Za-z0-9·（）()]+)\s*([一-龥]+?)\s*[纠案][纷件]/,
      /民事判决书\s*\n\s*(.+)/,
      /刑事判决书\s*\n\s*(.+)/,
      /行政判决书\s*\n\s*(.+)/,
    ]
    for (const pat of titlePatterns) {
      const m = head.match(pat)
      if (m) {
        if (m.length >= 4 && m[2]) {
          result.title = `${m[1]}诉${m[2]}${m[3] || ''}纠纷案`
        } else if (m[1]) {
          result.title = m[1].replace(/^\s+/, '').slice(0, 60)
          if (!result.title.endsWith('案')) result.title += '案'
        }
        break
      }
    }
  }
  // 法院：常见格式
  const courtPatterns = [
    /([一-龥]{2,12}(省|市|自治区|特别行政区)?(高级|中级|基层)?人民法院)/,
    /([一-龥]{2,15}法院)/,
  ]
  for (const pat of courtPatterns) {
    const m = head.match(pat)
    if (m) { result.court = m[1]; break }
  }

  // 法院层级
  if (result.court) {
    if (result.court.includes('最高')) result.court_level = 'supreme'
    else if (result.court.includes('高级')) result.court_level = 'high'
    else if (result.court.includes('中级')) result.court_level = 'intermediate'
    else if (result.court.includes('基层') || result.court.includes('区') || result.court.includes('县')) result.court_level = 'basic'
  }

  // 审判程序
  if (head.includes('二审') || head.includes('二审')) result.trial_procedure = 'second'
  else if (head.includes('再审') || head.includes('再审')) result.trial_procedure = 'retrial'
  else if (head.includes('审判监督')) result.trial_procedure = 'supervision'

  // 日期：支持中文数字 二〇二四年五月十日 / 2024年5月10日
  const datePatterns = [
    /(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/,
    /(\d{4})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(\d{1,2})/,
    /([一-鿿\d〇○]{2,6})\s*年\s*([一-鿿\d〇○]{1,3})\s*月\s*([一-鿿\d〇○]{1,3})\s*日/,
  ]
  for (const pat of datePatterns) {
    const m = head.match(pat)
    if (m) {
      let y = parseCnOrDigit(m[1]), mo = parseCnOrDigit(m[2]), d = parseCnOrDigit(m[3])
      if (y && mo && d) {
        result.judgment_date = `${y}-${mo.padStart(2,'0')}-${d.padStart(2,'0')}`
        break
      }
    }
  }

  // 法院：也尝试从 case_no 推断
  if (!result.court && result.case_no) {
    const regionMap: Record<string, string> = {
      '京':'北京市', '沪':'上海市', '津':'天津市', '渝':'重庆市',
      '冀':'河北省', '晋':'山西省', '辽':'辽宁省', '吉':'吉林省', '黑':'黑龙江省',
      '苏':'江苏省', '浙':'浙江省', '皖':'安徽省', '闽':'福建省', '赣':'江西省',
      '鲁':'山东省', '豫':'河南省', '鄂':'湖北省', '湘':'湖南省',
      '粤':'广东省', '琼':'海南省', '川':'四川省', '黔':'贵州省', '滇':'云南省',
      '陕':'陕西省', '甘':'甘肃省', '青':'青海省', '台':'台湾省',
      '蒙':'内蒙古', '桂':'广西', '藏':'西藏', '宁':'宁夏', '新':'新疆',
    }
    const abbr = result.case_no.replace(/^[（(]\d{4}[）)]/, '').charAt(0)
    const region = regionMap[abbr]
    if (region) {
      if (result.case_no.includes('最高')) result.court = '最高人民法院'
      else if (result.case_no.includes('高') || (result.court_level === 'high')) result.court = `${region}高级人民法院`
      else if (result.case_no.includes('中') || result.case_no.match(/[（(]\d{4}[）)]\D{2,4}中/) || result.court_level === 'intermediate') result.court = `${region}第${abbr === '京' ? '二' : '一'}中级人民法院`
      else result.court = `${region}人民法院`
    }
  }

  // 法官
  const judgePatterns = [
    /(审判员|审判长|代理审判员|人民陪审员)\s*[：:]\s*([一-龥]{2,4})/,
    /(审判员|审判长|代理审判员|人民陪审员)\s+([一-龥]{2,4})/,
  ]
  for (const pat of judgePatterns) {
    const m = head.match(pat)
    if (m) { result.judge_name = m[2]; break }
  }

  // 案由：从内容或标题提取
  const causePatterns = [
    /([一-龥]{2,12}(合同|劳动|交通|离婚|继承|侵权|行政|刑事|知识|公司|海事|票据|借贷|买卖|租赁|承包|抵押|保证|合伙|保险|证券|不正当竞争|垄断|环境|土地|房产|建筑|物业|医疗|教育|网络|名誉|肖像|抚养|变更|变更抚养|股权|转让|执行|竞业|著作权|商标|专利|人格)[一-龥]*[纠案][纷件])/,
    /案\s*由\s*[：:]\s*([一-龥]{2,30})/,
  ]
  for (const pat of causePatterns) {
    const m = head.match(pat)
    if (m) { result.case_category_2 = m[1].replace(/\s+/g, ''); break }
  }
  // 从标题回退提取案由
  if (!result.case_category_2 && result.title) {
    const tm = result.title.match(/[一-龥A-Za-z0-9·]+?([一-龥]+(?:纠纷|争议|赔偿|确认|认定|关系|责任|合同|权)[一-龥]*)案$/)
    if (tm) result.case_category_2 = tm[1]
  }
  // 推断案由一级
  if (result.case_category_2) {
    const cat = result.case_category_2
    if (/行政|处罚|许可|征收/.test(cat)) result.case_category_1 = '行政'
    else if (/刑事|罪|诈骗|盗窃|贪污|受贿/.test(cat)) result.case_category_1 = '刑事'
    else result.case_category_1 = '民事'
  }

  return result
}

/** 解析中文或数字：五→5, 十→10, 十一→11, 二十→20, 2024→2024 */
function parseCnOrDigit(s: string): string | null {
  if (!s) return null
  if (/^\d+$/.test(s)) return s
  const cnNums: Record<string, string> = {
    '〇':'0','○':'0','零':'0','一':'1','二':'2','三':'3','四':'4',
    '五':'5','六':'6','七':'7','八':'8','九':'9',
  }
  // 年份：二〇二四 → 2024
  if (s.length === 4) {
    const m = [...s].map(c => cnNums[c] || c).join('')
    if (/^\d{4}$/.test(m)) return m
  }
  // 月/日
  if (s === '十') return '10'
  let v = 0
  let rest = s
  if (rest.startsWith('二十')) { v = 20; rest = rest.slice(2) }
  else if (rest.startsWith('三十')) { v = 30; rest = rest.slice(2) }
  else if (rest.startsWith('十')) { v = 10; rest = rest.slice(1) }
  if (!rest) return String(v)
  const idx = '一二三四五六七八九'.indexOf(rest)
  if (idx >= 0) return String(v + idx + 1)
  // fallback: 字符映射
  const mapped = [...rest].map(c => cnNums[c] || c).join('')
  return /^\d+$/.test(mapped) ? mapped : null
}

/** 处理文件上传——批量模式 */
function handleBatchFileUpload(file: any) {
  uploadingFile.value = true
  const reader = new FileReader()
  reader.onload = (e) => {
    const text = e.target?.result as string
    if (text) {
      const meta = extractMeta(text, file.name)
      const bc = emptyBatchCase()
      bc.file_name = file.name
      bc.full_text = text
      Object.assign(bc, meta)
      batchCases.value.push(bc)
    }
    uploadingFile.value = false
  }
  reader.onerror = () => {
    uploadingFile.value = false
    ElMessage.error(`文件 ${file.name} 读取失败`)
  }
  reader.readAsText(file, "UTF-8")
  return false
}

/** 手动添加一个空白表单 */
function addManualCase() {
  batchCases.value.push(emptyBatchCase())
}

/** 删除批量列表中的一项 */
function removeBatchItem(uid: string) {
  batchCases.value = batchCases.value.filter(c => c.uid !== uid)
}

onMounted(async () => {
  await loadData()
})

async function refreshAll() {
  await loadData()
  if (caseView.value === "completed") loadCompletedCases()
  else if (caseView.value === "unpublished") loadUnpublishedCases()
}

async function loadData() {
  loading.value = true
  try {
    const [statsRes, casesRes] = await Promise.all([
      api.get("/admin/stats"),
      api.get("/admin/cases/pending-review", { params: { page_size: 500 } }),
    ])
    stats.value = statsRes.data
    pendingCases.value = casesRes.data.items || []
    totalPending.value = casesRes.data.total || 0
  } catch {
    ElMessage.error("加载失败，请确认你有管理员权限")
  } finally {
    loading.value = false
  }
}

function openSubmitDialog() {
  batchCases.value = []
  showSubmitDialog.value = true
}

async function submitBatchCases() {
  const valid = batchCases.value.filter(c => c.title.trim() && c.case_no.trim() && c.full_text.trim())
  if (valid.length === 0) {
    ElMessage.warning("没有有效的案例（案号、标题、全文均为必填），请先上传判决书文件")
    return
  }
  submitting.value = true
  try {
    const payload = valid.map(c => ({
      case_no: c.case_no.trim(), title: c.title.trim(), court: c.court.trim(),
      court_level: c.court_level, court_region: c.court_region.trim(),
      judge_name: c.judge_name.trim(), trial_procedure: c.trial_procedure,
      case_category_1: c.case_category_1.trim(), case_category_2: c.case_category_2.trim(),
      case_category_3: c.case_category_3.trim(), judgment_date: c.judgment_date,
      full_text: c.full_text.trim(), summary: c.summary.trim(),
      ruling_abstract: c.ruling_abstract.trim(),
    }))
    const res = await api.post("/admin/cases/batch", { cases: payload })
    const skipped = res.data.skipped || []
    showSubmitDialog.value = false

    if (skipped.length) {
      // 情况2：部分重复——不自动消失，点确认或空白处关闭
      const dupList = skipped.map((s: any) =>
        `<p style="margin:4px 0">「<b>${s.title}</b>」→ 已有：${s.dup_case_no}</p>`
      ).join('')
      ElMessageBox({
        title: "部分提交成功",
        message: `<p>成功提交 <b>${res.data.count}</b> 个案例。</p>
         <p style="margin-top:8px">以下 <b>${skipped.length}</b> 个重复案例已跳过：</p>
         <div style="text-align:left;max-height:200px;overflow-y:auto;margin-top:4px">${dupList}</div>`,
        type: "warning",
        dangerouslyUseHTMLString: true,
        closeOnClickModal: true,
        showCancelButton: false,
        confirmButtonText: "知道了",
      })
    } else {
      // 情况1：全部成功——0.5秒自动消失，也可点击空白处消失
      ElMessageBox.alert(
        `成功提交 <b>${res.data.count}</b> 个案例`,
        "提交成功",
        {
          type: "success" as any,
          dangerouslyUseHTMLString: true,
          closeOnClickModal: true,
          confirmButtonText: "确定",
          showClose: false,
        },
      )
      setTimeout(() => ElMessageBox.close(), 500)
    }
    await loadData()
  } catch (e: any) {
    const resp = e?.response
    const status = resp?.status
    const detail = resp?.data?.detail || `请求失败 (${status || '无响应'})`
    if (status === 409) {
      ElMessageBox.alert(detail, "提交失败", {
        type: "error", confirmButtonText: "知道了", closeOnClickModal: true,
      })
    } else {
      ElMessageBox.alert(detail, "提交失败", {
        type: "error", confirmButtonText: "知道了", closeOnClickModal: true,
      })
    }
  } finally {
    submitting.value = false
  }
}

async function loadUsers() {
  showUsers.value = true
  try {
    const res = await api.get("/admin/users")
    users.value = res.data.items || []
  } catch {
    ElMessage.error("加载用户列表失败")
  }
}

async function updateUserRole(userId: number, role: string) {
  try {
    await api.put(`/admin/users/${userId}/role`, { role })
    ElMessage.success("角色已更新")
    loadUsers()
  } catch {
    ElMessage.error("更新失败")
  }
}

async function toggleUserLock(userId: number, locked: boolean) {
  try {
    await api.put(`/admin/users/${userId}/lock`, { is_locked: locked })
    ElMessage.success(locked ? "用户已锁定" : "用户已解锁")
    loadUsers()
  } catch {
    ElMessage.error("操作失败")
  }
}

async function deleteUser(userId: number) {
  try {
    await ElMessageBox.confirm("确定注销该用户？此操作不可恢复。", "注销用户", {
      confirmButtonText: "确认注销",
      cancelButtonText: "取消",
      type: "error",
    })
  } catch {
    return
  }
  try {
    await api.delete(`/admin/users/${userId}`)
    ElMessage.success("用户已注销")
    loadUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "注销失败")
  }
}

// 已通过 / 下架案例
const caseView = ref<"pending" | "completed" | "unpublished">("pending")
const completedCases = ref<any[]>([])
const unpublishedCases = ref<any[]>([])
const loadingCompleted = ref(false)
const completedSearch = ref("")
const PAGE_SIZE = 20
const completedPage = ref(1)
const unpublishedPage = ref(1)

const filteredCompleted = computed(() => {
  let list = completedCases.value
  if (completedSearch.value) {
    const q = completedSearch.value.toLowerCase()
    list = list.filter(
      (c: any) => (c.case_no || "").includes(q) || (c.title || "").toLowerCase().includes(q)
    )
  }
  const start = (completedPage.value - 1) * PAGE_SIZE
  return list.slice(start, start + PAGE_SIZE)
})
const completedTotal = computed(() => {
  if (completedSearch.value) {
    const q = completedSearch.value.toLowerCase()
    return completedCases.value.filter(
      (c: any) => (c.case_no || "").includes(q) || (c.title || "").toLowerCase().includes(q)
    ).length
  }
  return completedCases.value.length
})

const pagedUnpublished = computed(() => {
  const start = (unpublishedPage.value - 1) * PAGE_SIZE
  return unpublishedCases.value.slice(start, start + PAGE_SIZE)
})

async function loadCompletedCases() {
  loadingCompleted.value = true
  try {
    const res = await api.get("/admin/cases/completed", { params: { page_size: 500 } })
    completedCases.value = res.data.items || []
  } catch {
    ElMessage.error("加载已通过案例失败")
  } finally {
    loadingCompleted.value = false
  }
}

async function loadUnpublishedCases() {
  loadingCompleted.value = true
  try {
    const res = await api.get("/admin/cases/unpublished", { params: { page_size: 500 } })
    unpublishedCases.value = res.data.items || []
  } catch { ElMessage.error("加载失败") }
  finally { loadingCompleted.value = false }
}

function switchView(v: "pending" | "completed" | "unpublished") {
  caseView.value = v
  if (v === "completed") loadCompletedCases()
  else if (v === "unpublished") loadUnpublishedCases()
}

watch(completedSearch, () => { completedPage.value = 1 })

async function review(caseId: number, action: string, reviseData?: any) {
  if (action === "delete") {
    try {
      await ElMessageBox.confirm("确定永久删除该案例？此操作不可撤销。", "确认删除", {
        confirmButtonText: "永久删除", cancelButtonText: "取消", type: "error",
      })
    } catch { return }
  }
  try {
    await api.post(`/admin/cases/${caseId}/review`, { action, ...(reviseData || {}) })
    const labels: Record<string, string> = { confirm: "已确认", reject: "已驳回", unpublish: "已下架", restore: "已撤回", delete: "已删除" }
    ElMessage.success(labels[action] || "操作成功")
    if (action === "confirm" || action === "reject") {
      pendingCases.value = pendingCases.value.filter(c => c.id !== caseId)
      totalPending.value--
    }
    if (caseView.value === "completed") loadCompletedCases()
    else if (caseView.value === "unpublished") loadUnpublishedCases()
    loadData()  // 刷新统计数字
  } catch {
    ElMessage.error("操作失败")
  }
}

function showReviseDialog(caseItem: any) {
  ElMessageBox.prompt("请输入修正后的摘要", "修正AI摘要", {
    confirmButtonText: "确认修正",
    inputValue: caseItem.summary || "",
    inputType: "textarea",
  }).then(({ value }: any) => {
    review(caseItem.id, "revise", { summary: value })
  }).catch(() => {})
}
</script>

<template>
  <GridScan :sensitivity="0.55" :line-thickness="1" lines-color="#A855F7" :grid-scale="0.1" scan-color="#000000" :scan-opacity="0.4" :bloom-intensity="0.6" :chromatic-aberration="0.004" :noise-intensity="0.01" :interactive="true" />
  <div class="admin-page" style="max-width: 1200px; margin: 0 auto; position: relative; z-index: 1">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px">
      <div>
        <h3 class="admin-heading">管理后台</h3>
        <p class="admin-subtitle">案例审核 · 用户管理 · 系统统计</p>
      </div>
      <div style="display:flex;gap:8px" class="admin-toolbar">
        <button class="submit-case-btn" @click="openSubmitDialog">
          <span class="submit-case-text">提交新案例</span>
          <span class="submit-case-icon">
            <svg fill="none" height="24" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" viewBox="0 0 24 24" width="24" xmlns="http://www.w3.org/2000/svg">
              <line x1="12" x2="12" y1="5" y2="19"></line>
              <line x1="5" x2="19" y1="12" y2="12"></line>
            </svg>
          </span>
        </button>
        <el-button :icon="User" @click="loadUsers" :type="showUsers ? 'primary' : 'default'">
          {{ showUsers ? '用户列表' : '用户管理' }}
        </el-button>
        <el-button :icon="Refresh" @click="refreshAll" :loading="loading">刷新</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" style="margin-bottom:20px">
      <el-col :span="6">
        <el-card shadow="hover" class="admin-stat">
          <div class="admin-stat-num"><CountUp :to="stats.total_cases || 0" /></div>
          <div class="admin-stat-label">案例总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="admin-stat">
          <div class="admin-stat-num"><CountUp :to="stats.total_users || 0" /></div>
          <div class="admin-stat-label">注册用户</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="admin-stat">
          <div class="admin-stat-num" style="color:var(--accent-blue)"><CountUp :to="totalPending" /></div>
          <div class="admin-stat-label">待审核</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="admin-stat">
          <div class="admin-stat-num" style="color:var(--accent-red)"><CountUp :to="stats.detail?.filter((d: any) => d.status === 'unpublished')[0]?.count || 0" /></div>
          <div class="admin-stat-label">已下架</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 案例状态分布 -->
    <el-card shadow="never" style="margin-bottom:20px">
      <h4 style="margin-bottom:12px;color:var(--text-primary)">📊 案例处理状态分布（实时）</h4>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <el-tag
          v-for="item in stats.detail" :key="item.status"
          size="large"
          :type="item.type"
          effect="plain"
          style="padding:6px 14px;font-size:13px"
        >
          {{ item.label }}：<b>{{ item.count }}</b>
        </el-tag>
      </div>
      <p v-if="!stats.detail?.length" style="color:var(--text-tertiary);font-size:13px;text-align:center;padding:12px">暂无案例数据</p>
    </el-card>

    <!-- 用户管理 -->
    <el-card v-if="showUsers" shadow="never" style="margin-bottom:20px">
      <h4 style="margin-bottom:12px;color:var(--text-primary)">用户列表</h4>
      <el-table :data="users" border stripe>
        <el-table-column label="序号" width="60" type="index" />
        <el-table-column label="邮箱" min-width="160">
          <template #default="{ row }">
            {{ row.email || (row.phone ? '无' : '—') }}
          </template>
        </el-table-column>
        <el-table-column label="电话号码" min-width="140">
          <template #default="{ row }">
            {{ row.phone || '未绑定' }}
          </template>
        </el-table-column>
        <el-table-column prop="nickname" label="昵称" width="120" />
        <el-table-column label="角色" width="160">
          <template #default="{ row }">
            <el-select
              :model-value="row.role === 'user' ? 'normal' : row.role"
              size="small"
              @change="(val: string) => updateUserRole(row.id, val)"
            >
              <el-option label="普通用户" value="normal" />
              <el-option label="会员" value="premium" />
              <el-option label="管理员" value="admin" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_locked ? 'danger' : 'success'" size="small">
              {{ row.is_locked ? '已锁定' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="搜索/阅读" width="120">
          <template #default="{ row }">
            {{ row.search_count || 0 }} / {{ row.read_count || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <button
              v-if="row.id !== 5"
              class="user-del-btn"
              @click="deleteUser(row.id)"
              :disabled="row.id === auth.user?.id"
              :title="row.id === auth.user?.id ? '不能注销自己' : '注销用户'"
            >
              <svg class="trash-svg" viewBox="0 -10 64 74" xmlns="http://www.w3.org/2000/svg">
                <g><rect x="16" y="24" width="32" height="30" rx="3" ry="3" fill="#e74c3c"/><g transform-origin="12 18" id="lid-group"><rect x="12" y="12" width="40" height="6" rx="2" ry="2" fill="#c0392b"/><rect x="26" y="8" width="12" height="4" rx="2" ry="2" fill="#c0392b"/></g></g>
              </svg>
            </button>
            <span v-else style="font-size:11px;color:#484F58">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- AI 加工审核 -->
    <el-card shadow="never">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h4 style="color:var(--text-primary);margin:0">
          {{ caseView === 'completed' ? '已通过案例' : caseView === 'unpublished' ? '下架案例' : '待审核案例' }}
        </h4>
        <div style="display:flex;gap:6px">
          <el-button size="small" :type="caseView === 'pending' ? 'primary' : 'default'" @click="switchView('pending')">待审核</el-button>
          <el-button size="small" :type="caseView === 'completed' ? 'primary' : 'default'" @click="switchView('completed')">已通过</el-button>
          <el-button size="small" :type="caseView === 'unpublished' ? 'primary' : 'default'" @click="switchView('unpublished')">下架案例</el-button>
        </div>
      </div>

      <!-- 待审核表格 -->
      <template v-if="caseView === 'pending'">
      <el-table :data="pendingCases" border stripe v-loading="loading" empty-text="暂无待审核案例">
        <el-table-column prop="case_no" label="案号" width="200" />
        <el-table-column label="标题" min-width="200">
          <template #default="{ row }">
            <span class="cell-link" @click="showDetail('标题', row.title)">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="case_category_2" label="案由" width="140" />
        <el-table-column prop="court" label="法院" width="120" />
        <el-table-column label="摘要" min-width="200">
          <template #default="{ row }">
            <span class="cell-link" @click="showDetail('摘要', row.summary || row.full_text || '')">{{ row.summary || (row.full_text || '').slice(0, 80) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <button class="approve-btn" @click="review(row.id, 'confirm')"><span class="apv-text">通过</span><span class="apv-icon"><svg viewBox="0 0 24 24" height="18" width="18"><path d="M9.707 19.121a.997.997 0 0 1-1.414 0l-5.646-5.647a1.5 1.5 0 0 1 0-2.121l.707-.707a1.5 1.5 0 0 1 2.121 0L9 14.171l9.525-9.525a1.5 1.5 0 0 1 2.121 0l.707.707a1.5 1.5 0 0 1 0 2.121z" fill="#eee"/></svg></span></button>
              <button class="reject-btn" @click="review(row.id, 'reject')"><span class="rjt-text">驳回</span><span class="rjt-icon"><svg viewBox="0 0 512 512" width="18" height="18"><path d="M112,112l20,320c.95,18.49,14.4,32,32,32H348c17.67,0,30.87-13.51,32-32l20-320" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-linejoin:round;stroke-width:32px"/><line style="stroke:#fff;stroke-linecap:round;stroke-miterlimit:10;stroke-width:32px" x1="80" x2="432" y1="112" y2="112"/><path d="M192,112V72h0a23.93,23.93,0,0,1,24-24h80a23.93,23.93,0,0,1,24,24h0v40" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-linejoin:round;stroke-width:32px"/><line style="fill:none;stroke:#fff;stroke-linecap:round;stroke-linejoin:round;stroke-width:32px" x1="256" x2="256" y1="176" y2="400"/><line style="fill:none;stroke:#fff;stroke-linecap:round;stroke-linejoin:round;stroke-width:32px" x1="184" x2="192" y1="176" y2="400"/><line style="fill:none;stroke:#fff;stroke-linecap:round;stroke-linejoin:round;stroke-width:32px" x1="328" x2="320" y1="176" y2="400"/></svg></span></button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      </template>

      <!-- 已通过表格 -->
      <template v-else-if="caseView === 'completed'">
        <div style="margin-bottom:8px">
          <el-input v-model="completedSearch" placeholder="搜索案号或标题..." size="small" style="width:280px" clearable />
        </div>
        <el-table :data="filteredCompleted" border stripe v-loading="loadingCompleted" empty-text="暂无已通过案例">
          <el-table-column prop="case_no" label="案号" width="200" />
          <el-table-column label="标题" min-width="200">
            <template #default="{ row }">
              <span class="cell-link" @click="showDetail('标题', row.title)">{{ row.title }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="case_category_2" label="案由" width="140" />
          <el-table-column prop="court" label="法院" width="120" />
          <el-table-column label="摘要" min-width="200">
            <template #default="{ row }">
              <span class="cell-link" @click="showDetail('摘要', row.summary || row.full_text || '')">{{ row.summary || (row.full_text || '').slice(0, 80) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="warning" @click="review(row.id, 'unpublish')">下架</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div style="display:flex;justify-content:center;align-items:center;gap:12px;margin-top:12px">
          <el-button size="small" :disabled="completedPage <= 1" @click="completedPage--">上一页</el-button>
          <span style="font-size:13px;color:var(--text-tertiary)">
            {{ completedPage }} / {{ Math.max(1, Math.ceil(completedTotal / PAGE_SIZE)) }}（共 {{ completedTotal }} 条）
          </span>
          <el-button size="small" :disabled="completedPage >= Math.ceil(completedTotal / PAGE_SIZE)" @click="completedPage++">下一页</el-button>
        </div>
      </template>

      <!-- 下架案例表格 -->
      <template v-else>
        <el-table :data="pagedUnpublished" border stripe v-loading="loadingCompleted" empty-text="暂无下架案例">
          <el-table-column prop="case_no" label="案号" width="200" />
          <el-table-column label="标题" min-width="200">
            <template #default="{ row }">
              <span class="cell-link" @click="showDetail('标题', row.title)">{{ row.title }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="case_category_2" label="案由" width="140" />
          <el-table-column prop="court" label="法院" width="120" />
          <el-table-column label="摘要" min-width="200">
            <template #default="{ row }">
              <span class="cell-link" @click="showDetail('摘要', row.summary || row.full_text || '')">{{ row.summary || (row.full_text || '').slice(0, 80) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="success" @click="review(row.id, 'restore')">撤回</el-button>
              <el-button size="small" type="danger" @click="review(row.id, 'delete')">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div style="display:flex;justify-content:center;align-items:center;gap:12px;margin-top:12px">
          <el-button size="small" :disabled="unpublishedPage <= 1" @click="unpublishedPage--">上一页</el-button>
          <span style="font-size:13px;color:var(--text-tertiary)">
            {{ unpublishedPage }} / {{ Math.max(1, Math.ceil(unpublishedCases.length / PAGE_SIZE)) }}（共 {{ unpublishedCases.length }} 条）
          </span>
          <el-button size="small" :disabled="unpublishedPage >= Math.ceil(unpublishedCases.length / PAGE_SIZE)" @click="unpublishedPage++">下一页</el-button>
        </div>
      </template>
    </el-card>

    <!-- 批量提交案例弹窗 -->
    <el-dialog v-model="showSubmitDialog" title="批量提交案例" width="960px" :close-on-click-modal="false">
      <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
        <span style="font-size:13px;color:var(--text-tertiary)">上传判决书文件（支持 .txt），自动提取案号、标题等信息：</span>
        <el-upload
          :show-file-list="false"
          accept=".txt"
          multiple
          :before-upload="handleBatchFileUpload"
          :disabled="uploadingFile"
        >
          <el-button size="small" type="primary" :loading="uploadingFile" :icon="Upload">
            {{ uploadingFile ? '读取中...' : '批量上传判决书' }}
          </el-button>
        </el-upload>
        <el-button size="small" :icon="Plus" @click="addManualCase">手动添加</el-button>
      </div>

      <!-- 批量案例列表 -->
      <div v-if="batchCases.length" style="max-height:460px;overflow-y:auto">
        <el-card v-for="(c, idx) in batchCases" :key="c.uid" shadow="hover" style="margin-bottom:10px">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="font-weight:600;font-size:13px">
                <el-tag size="small" type="info" style="margin-right:8px">#{{ idx + 1 }}</el-tag>
                {{ c.file_name || '手动录入' }}
              </span>
              <el-button size="small" text type="danger" :icon="Delete" @click="removeBatchItem(c.uid)">移除</el-button>
            </div>
          </template>
          <el-row :gutter="8">
            <el-col :span="8">
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">案号 *</span>
                <el-input v-model="c.case_no" size="small" placeholder="(2025)京01民终12345号" />
              </div>
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">法院</span>
                <el-input v-model="c.court" size="small" placeholder="法院名称" />
              </div>
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">案由一级</span>
                <el-input v-model="c.case_category_1" size="small" placeholder="民事/刑事/行政" />
              </div>
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">审判程序</span>
                <el-select v-model="c.trial_procedure" size="small" style="width:100%">
                  <el-option label="一审" value="first" /><el-option label="二审" value="second" />
                  <el-option label="再审" value="retrial" /><el-option label="审判监督" value="supervision" />
                </el-select>
              </div>
            </el-col>
            <el-col :span="8">
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">标题 *</span>
                <el-input v-model="c.title" size="small" placeholder="案件标题" />
              </div>
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">法院层级</span>
                <el-select v-model="c.court_level" size="small" style="width:100%">
                  <el-option label="最高人民法院" value="supreme" /><el-option label="高级" value="high" />
                  <el-option label="中级" value="intermediate" /><el-option label="基层" value="basic" />
                </el-select>
              </div>
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">案由二级</span>
                <el-input v-model="c.case_category_2" size="small" placeholder="案由" />
              </div>
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">判决日期</span>
                <el-input v-model="c.judgment_date" size="small" placeholder="YYYY-MM-DD" />
              </div>
            </el-col>
            <el-col :span="8">
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">法官</span>
                <el-input v-model="c.judge_name" size="small" placeholder="法官姓名" />
              </div>
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">地域</span>
                <el-input v-model="c.court_region" size="small" placeholder="如：北京" />
              </div>
              <div style="margin-bottom:6px"><span style="font-size:11px;color:var(--text-tertiary)">案由三级</span>
                <el-input v-model="c.case_category_3" size="small" placeholder="子案由" />
              </div>
            </el-col>
          </el-row>
          <div style="margin-top:4px">
            <span style="font-size:11px;color:var(--text-tertiary)">判决书全文 *（{{ c.full_text.length }}字）</span>
            <el-input v-model="c.full_text" type="textarea" :rows="6" size="small" placeholder="判决书全文" />
          </div>
        </el-card>
      </div>
      <el-empty v-else description="请上传判决书文件或手动添加案例" :image-size="60" />

      <template #footer>
        <el-button @click="showSubmitDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitBatchCases">
          批量提交（{{ batchCases.filter(c => c.title && c.case_no && c.full_text).length }}/{{ batchCases.length }} 有效）
        </el-button>
      </template>
    </el-dialog>

    <!-- 点击查看完整内容弹窗 -->
    <el-dialog v-model="detailVisible" :title="detailTitle" width="700px" :close-on-click-modal="true">
      <div style="white-space:pre-wrap;word-break:break-word;line-height:1.8;max-height:500px;overflow-y:auto;font-size:14px;color: rgba(255,255,255,0.85)">{{ detailContent }}</div>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ——— 管理员统计卡片（毛玻璃） ——— */
.admin-stat {
  text-align: center; padding: 20px 16px;
  border-radius: 16px; border: none !important;
  background: rgba(255, 255, 255, 0.025) !important;
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) !important;
  transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}
.admin-stat:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.06) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.15), 0 8px 32px rgba(0, 0, 0, 0.3) !important;
}
.admin-stat-num { font-size: 28px; font-weight: 700; color: rgba(180, 220, 255, 0.92); margin-top: 4px; }
.admin-stat-label { font-size: 12px; color: rgba(255, 255, 255, 0.65); font-weight: 500; letter-spacing: 0.03em; }

/* ——— 页面标题 ——— */
.admin-heading { color: rgba(255, 255, 255, 0.95); font-size: 22px; font-weight: 700; }
.admin-subtitle { color: rgba(255, 255, 255, 0.60); font-size: 13px; }

/* 可点击查看详情的表格单元格 */
.cell-link {
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
  transition: color 0.15s;
}
.cell-link:hover { color: rgba(180, 220, 255, 0.95); }

/* ——— 内容卡片（毛玻璃） ——— */
.admin-card-title { color: rgba(255, 255, 255, 0.90); margin-bottom: 12px; font-weight: 600; }

/* ——— 管理员专属底图 ——— */
.admin-bg {
  position: fixed; inset: 0; z-index: 0;
  background: url('/admin-bg.png') center / cover no-repeat;
  pointer-events: none;
}

.approve-btn {
  width: 80px; height: 32px; cursor: pointer; display: flex; align-items: center;
  background: #16a34a; border: none; border-radius: 5px;
  box-shadow: 1px 1px 3px rgba(0,0,0,0.15); padding: 0; position: relative;
  overflow: hidden;
}
.approve-btn, .approve-btn span { transition: 200ms; }
.apv-text { color: #fff; font-weight: bold; font-size: 12px; margin: 0 auto; }
.apv-icon {
  position: absolute; left: 0; top: 0; height: 100%; width: 100%;
  display: flex; align-items: center; justify-content: center;
  transform: translateX(-100%); border-right: none;
}
.approve-btn:hover { background: #15803d; }
.approve-btn:hover .apv-text { color: transparent; }
.approve-btn:hover .apv-icon { transform: translateX(0); }

.reject-btn {
  width: 80px; height: 32px; cursor: pointer; display: flex; align-items: center;
  background: #dc2626; border: 1px solid #b91c1c; border-radius: 5px;
  padding: 0; position: relative; overflow: hidden;
}
.reject-btn, .reject-btn span { transition: 200ms; }
.rjt-text { color: #fff; font-weight: 600; font-size: 12px; margin: 0 auto; }
.rjt-icon {
  position: absolute; left: 0; top: 0; height: 100%; width: 100%;
  display: flex; align-items: center; justify-content: center;
  transform: translateX(-100%); background: #b91c1c;
}
.reject-btn:hover { background: #b91c1c; }
.reject-btn:hover .rjt-text { color: transparent; }
.reject-btn:hover .rjt-icon { transform: translateX(0); }
.op-btns { display: flex; justify-content: center; align-items: center; gap: 8px; }
</style>

<style>
/* ——— 管理员页面全局暗色覆盖（非 scoped，仅本页生效） ——— */
/* 覆盖 CSS 变量为浅色，内联 var(--text-*) 自动生效 */
.admin-page {
  --text-primary: rgba(255, 255, 255, 0.93);
  --text-secondary: rgba(255, 255, 255, 0.80);
  --text-tertiary: rgba(255, 255, 255, 0.62);
  --text-muted: rgba(255, 255, 255, 0.42);
  --bg-input: rgba(255, 255, 255, 0.04);
}

.admin-page .el-card {
  background: rgba(255, 255, 255, 0.008) !important;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: none !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.03) !important;
  border-radius: 16px !important;
}

.admin-page .el-card__header {
  border-bottom-color: rgba(255, 255, 255, 0.08) !important;
  color: rgba(255, 255, 255, 0.92);
}

.admin-page .el-card__body { color: rgba(255, 255, 255, 0.82); }
.admin-page .el-card__body h4 { color: rgba(255, 255, 255, 0.90); }

/* 表格表头更亮 */
/* 表格 */
.admin-page .el-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.04);
  --el-table-border-color: rgba(255, 255, 255, 0.06);
  --el-table-row-hover-bg-color: rgba(255, 255, 255, 0.05);
  background: transparent !important;
  color: rgba(255, 255, 255, 0.85) !important;
}
.admin-page .el-table th.el-table__cell {
  background: rgba(255, 255, 255, 0.04) !important;
  color: rgba(255, 255, 255, 0.75) !important;
  font-weight: 600; font-size: 12px;
  border-bottom-color: rgba(255, 255, 255, 0.08) !important;
}
.admin-page .el-table td.el-table__cell {
  border-bottom-color: rgba(255, 255, 255, 0.06) !important;
  color: rgba(255, 255, 255, 0.82) !important;
}
.admin-page .el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell {
  background: rgba(255, 255, 255, 0.02) !important;
}

/* 分页文字 */
.admin-page .el-pagination button,
.admin-page .el-pagination .el-pager li {
  color: rgba(255, 255, 255, 0.60) !important;
  background: transparent !important;
}
.admin-page .el-pagination .el-pager li.is-active {
  background: rgba(255, 255, 255, 0.12) !important;
  color: rgba(255, 255, 255, 0.92) !important;
}
.admin-page .el-pagination button:hover,
.admin-page .el-pagination .el-pager li:hover {
  color: rgba(255, 255, 255, 0.85) !important;
}

/* 默认按钮（独立 + 按钮组） */
.admin-page .el-button--default {
  background: rgba(255, 255, 255, 0.06) !important;
  border-color: rgba(255, 255, 255, 0.14) !important;
  color: rgba(255, 255, 255, 0.80) !important;
}
.admin-page .el-button--default:hover {
  background: rgba(255, 255, 255, 0.12) !important;
  border-color: rgba(255, 255, 255, 0.22) !important;
  color: rgba(255, 255, 255, 0.92) !important;
}
/* 主要按钮 */
.admin-page .el-button--primary {
  background: rgba(255, 255, 255, 0.14) !important;
  border-color: rgba(255, 255, 255, 0.20) !important;
  color: rgba(255, 255, 255, 0.94) !important;
}
.admin-page .el-button--primary:hover {
  background: rgba(255, 255, 255, 0.22) !important;
  color: #fff !important;
}

/* 标签 */
.admin-page .el-tag {
  background: rgba(255, 255, 255, 0.04) !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
  color: rgba(255, 255, 255, 0.85) !important;
}
.admin-page .el-tag b { color: rgba(180, 220, 255, 0.95); font-size: 15px; }

/* 输入框 */
.admin-page .el-input__wrapper {
  background: rgba(255, 255, 255, 0.04) !important;
  border: none !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.10) !important;
}
.admin-page .el-input__inner { color: rgba(255, 255, 255, 0.88) !important; }
.admin-page .el-input__inner::placeholder { color: rgba(255, 255, 255, 0.35) !important; }

/* 选择器 */
.admin-page .el-select__wrapper {
  background: rgba(255, 255, 255, 0.04) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.10) !important;
}
.admin-page .el-select__placeholder { color: rgba(255, 255, 255, 0.35) !important; }
.admin-page .el-select__selected-item { color: rgba(255, 255, 255, 0.88) !important; }

/* 对话框（含批量提交弹窗） */
.admin-page .el-dialog {
  background: rgba(20, 20, 30, 0.65) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.06) !important;
}
.admin-page .el-dialog__title { color: rgba(255, 255, 255, 0.93) !important; }
.admin-page .el-dialog__body {
  color: rgba(255, 255, 255, 0.78) !important;
  /* 弹窗内的 CSS 变量也覆盖 */
  --text-primary: rgba(255, 255, 255, 0.93);
  --text-secondary: rgba(255, 255, 255, 0.80);
  --text-tertiary: rgba(255, 255, 255, 0.62);
  --text-muted: rgba(255, 255, 255, 0.42);
}
.admin-page .el-dialog__header { border-bottom-color: rgba(255, 255, 255, 0.06) !important; }
.admin-page .el-dialog__footer { border-top-color: rgba(255, 255, 255, 0.06) !important; }

/* 空状态 */
.admin-page .el-empty__description p { color: rgba(255, 255, 255, 0.40) !important; }

/* 文本区域 */
.admin-page .el-textarea__inner {
  background: rgba(255, 255, 255, 0.04) !important;
  color: rgba(255, 255, 255, 0.88) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.10) !important;
}
.admin-page .el-textarea__inner::placeholder { color: rgba(255, 255, 255, 0.35) !important; }

/* 工具栏按钮间距统一 */
.admin-toolbar .el-button + .el-button { margin-left: 0 !important; }

/* 提交新案例按钮 */
.submit-case-btn {
  position: relative; width: 120px; height: 32px; cursor: pointer;
  display: flex; align-items: center; border: 1px solid #22c55e;
  background: #22c55e; border-radius: 8px; overflow: hidden;
  font-family: inherit; padding: 0; flex-shrink: 0;
}
.submit-case-btn:hover { background: #22c55e; }
.submit-case-btn:active { background: #16a34a; border-color: #16a34a; }
.submit-case-text {
  color: #f3f3f3; font-weight: 600; font-size: 12px;
  margin-left: 24px; transform: translateX(0);
  transition: transform 0.3s;
}
.submit-case-btn:hover .submit-case-text { transform: translateX(64px); }
.submit-case-icon {
  position: absolute; right: 0; height: 100%; width: 32px;
  background: #22c55e; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.3s;
}
.submit-case-btn:hover .submit-case-icon { width: 100%; left: 0; }
.submit-case-icon svg { width: 16px; color: #fff; }

/* 用户注销按钮 */
.user-del-btn {
  padding: 0; border: none; background: transparent; cursor: pointer;
  transition: transform 0.2s ease; flex-shrink: 0;
}
.user-del-btn:hover { transform: scale(1.1); }
.user-del-btn:active { transform: scale(0.95); }
.user-del-btn:disabled { opacity: 0.3; cursor: not-allowed; transform: none; }
.user-del-btn .trash-svg {
  width: 26px; height: 26px; transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1);
  overflow: visible;
}
.user-del-btn:hover .trash-svg { transform: rotate(3deg); }
.user-del-btn:hover #lid-group { transform: rotate(-28deg) translateY(2px); transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1); }
.user-del-btn:active #lid-group { transform: rotate(-12deg) scale(0.98); }
</style>
