<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import api from "@/api/client"
import { useAuthStore } from "@/stores/auth"
import {
  ArrowLeft, Star, Share, ArrowDown,
  View, Notebook, Loading, Switch,
} from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useSearchStore } from "@/stores/search"
import { useCompareBasketStore } from "@/stores/compareBasket"

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const searchStore = useSearchStore()
const basket = useCompareBasketStore()

function toggleCompare() {
  if (!caseData.value) return
  const c = caseData.value
  if (basket.hasCase(c.id)) {
    basket.removeCase(c.id)
    ElMessage.success("已移出对比")
  } else {
    if (basket.addCase({
      id: c.id,
      case_no: c.case_no,
      title: c.title || c.case_no,
      court: c.court || "",
      case_category_2: c.case_category_2 || "",
      judgment_date: c.judgment_date || "",
    })) {
      ElMessage.success("已加入对比")
    } else {
      ElMessage.warning("对比篮已满（最多5个案例）")
    }
  }
}

async function unpublishCase() {
  if (!caseData.value) return
  try {
    await ElMessageBox.confirm("确定下架该案例？下架后案例将不在检索结果中显示，管理员可撤回。", "下架案例", {
      confirmButtonText: "下架", cancelButtonText: "取消", type: "warning",
    })
  } catch { return }
  try {
    await api.post(`/admin/cases/${caseData.value.id}/review`, { action: "unpublish" })
    caseData.value.processing_status = "unpublished"
    searchStore.triggerRefresh()  // 通知检索页刷新
    ElMessage.success("已下架，返回检索页将不再显示此案例")
  } catch {
    ElMessage.error("下架失败")
  }
}

const caseData = ref<any>(null)
const related = ref<any[]>([])
const loading = ref(true)
const isFavorite = ref(false)
const favoriteGroupId = ref<number | null>(null)
const leftRatio = ref(50)
const fontSize = ref(16)
const showShareCard = ref(false)
const noteText = ref("")
const showNoteInput = ref(false)
const notes = ref<any[]>([])
const notesSection = ref<HTMLElement | null>(null)
const editingNoteId = ref<number | null>(null)
const editingNoteText = ref("")

// 收藏分组对话框
const showFavDialog = ref(false)
const selectedGroupId = ref<number | null>(null)
const groups = ref<any[]>([])
const showNewGroupInput = ref(false)
const newGroupName = ref("")
const newGroupDesc = ref("")
const creatingGroup = ref(false)

// 原文段落结构
const sections = computed(() => {
  if (!caseData.value?.full_text) return []
  const text = caseData.value.full_text
  const keywords = ["当事人", "原告", "被告", "诉讼请求", "辩称", "查明", "本院认为", "判决", "裁定", "依照"]
  const parts: { title: string; content: string }[] = []
  let current = { title: "全文", content: "" }
  for (const line of text.split("\n")) {
    const trimmed = line.trim()
    if (!trimmed) continue
    let matched = false
    for (const kw of keywords) {
      if (trimmed.startsWith(kw) && trimmed.length < 30) {
        if (current.content) parts.push({ ...current })
        current = { title: trimmed, content: "" }
        matched = true
        break
      }
    }
    if (!matched) current.content += line + "\n"
  }
  if (current.content) parts.push(current)
  if (parts.length === 0) parts.push({ title: "判决书全文", content: text })
  return parts
})

const activeSection = ref("")

async function loadCase(caseId: string) {
  loading.value = true
  caseData.value = null
  related.value = []
  notes.value = []
  showNoteInput.value = false
  favoriteGroupId.value = null
  const idNum = Number(caseId)
  try {
    const [detail, rel, favs, groupRes] = await Promise.all([
      api.get(`/case/${caseId}`),
      api.get(`/case/${caseId}/related`),
      auth.isLoggedIn ? api.get("/workspace/favorites") : Promise.resolve({ data: [] }),
      auth.isLoggedIn ? api.get("/workspace/groups") : Promise.resolve({ data: [] }),
    ])
    caseData.value = detail.data
    related.value = rel.data
    isFavorite.value = Array.isArray(favs.data)
      ? favs.data.some((f: any) => f.case_id === idNum)
      : false
    groups.value = Array.isArray(groupRes.data) ? groupRes.data : []

    // 检查是否已经加入某个分组
    if (auth.isLoggedIn) {
      for (const g of groups.value) {
        try {
          const itemsRes = await api.get(`/workspace/groups/${g.id}/items`)
          const items = Array.isArray(itemsRes.data) ? itemsRes.data : []
          if (items.some((item: any) => item.case_id === idNum)) {
            favoriteGroupId.value = g.id
            break
          }
        } catch {}
      }
    }

    // 如果是工作台笔记跳转，默认展开笔记
    if (route.query.showNotes === "1" && auth.isLoggedIn) {
      showNoteInput.value = true
      try {
        const notesRes = await api.get(`/workspace/notes/${caseId}`)
        notes.value = notesRes.data
      } catch {}
    }
  } catch {
    ElMessage.error("案例加载失败")
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadCase(route.params.id as string)
})

// 点击关联案例时，route.params.id 变化 → 重新加载
watch(() => route.params.id, (newId) => {
  if (newId) loadCase(newId as string)
})

async function toggleFavorite() {
  if (!auth.isLoggedIn) {
    ElMessage.warning("请先登录")
    return
  }
  const id = route.params.id as string
  if (isFavorite.value) {
    // 已收藏 → 直接取消
    try {
      await api.delete(`/workspace/favorites/${id}`)
      isFavorite.value = false
      favoriteGroupId.value = null
      ElMessage.success("已取消收藏")
    } catch {
      ElMessage.error("操作失败")
    }
    return
  }
  // 未收藏 → 弹出分组选择对话框
  selectedGroupId.value = favoriteGroupId.value
  showNewGroupInput.value = false
  newGroupName.value = ""
  newGroupDesc.value = ""
  showFavDialog.value = true
}

async function confirmFavorite() {
  if (!auth.isLoggedIn) return
  const id = route.params.id as string
  try {
    const body: any = {}
    if (selectedGroupId.value) {
      body.group_id = selectedGroupId.value
    }
    await api.post(`/workspace/favorites/${id}`, body)
    isFavorite.value = true
    favoriteGroupId.value = selectedGroupId.value
    showFavDialog.value = false
    ElMessage.success(selectedGroupId.value ? "已收藏并加入分组" : "已收藏")
  } catch (e: any) {
    if (e.response?.status === 400) {
      ElMessage.warning("该案例已收藏")
      isFavorite.value = true
      showFavDialog.value = false
    } else {
      ElMessage.error("操作失败")
    }
  }
}

async function createGroupAndSelect() {
  const name = newGroupName.value.trim()
  if (!name) {
    ElMessage.warning("请输入分组名称")
    return
  }
  creatingGroup.value = true
  try {
    const res = await api.post("/workspace/groups", {
      name,
      description: newGroupDesc.value.trim(),
    })
    const newGroup = { id: res.data.id, name, description: newGroupDesc.value.trim(), item_count: 0 }
    groups.value.push(newGroup)
    selectedGroupId.value = newGroup.id
    newGroupName.value = ""
    newGroupDesc.value = ""
    showNewGroupInput.value = false
    ElMessage.success("分组已创建并选中")
  } catch {
    ElMessage.error("创建分组失败")
  } finally {
    creatingGroup.value = false
  }
}

async function loadNotes() {
  if (!auth.isLoggedIn) return
  try {
    const res = await api.get(`/workspace/notes/${route.params.id}`)
    notes.value = res.data
  } catch {}
}

async function toggleNotes() {
  showNoteInput.value = !showNoteInput.value
  if (showNoteInput.value) {
    await loadNotes()
    await nextTick()
    notesSection.value?.scrollIntoView({ behavior: "smooth", block: "start" })
  }
}

async function addNote() {
  if (!noteText.value.trim()) return
  try {
    await api.post(`/workspace/notes/${route.params.id}`, {
      content: noteText.value,
      paragraph_ref: activeSection.value || undefined,
    })
    ElMessage.success("笔记已保存")
    noteText.value = ""
    await loadNotes()
  } catch {
    ElMessage.error("保存失败")
  }
}

function startEditNote(n: any) {
  editingNoteId.value = n.id
  editingNoteText.value = n.content
}

async function saveEditNote(noteId: number) {
  if (!editingNoteText.value.trim()) return
  try {
    await api.put(`/workspace/notes/${noteId}`, { content: editingNoteText.value })
    ElMessage.success("笔记已更新")
    editingNoteId.value = null
    editingNoteText.value = ""
    await loadNotes()
  } catch {
    ElMessage.error("更新失败")
  }
}

function cancelEdit() {
  editingNoteId.value = null
  editingNoteText.value = ""
}

async function deleteNote(noteId: number) {
  try {
    await api.delete(`/workspace/notes/${noteId}`)
    notes.value = notes.value.filter(n => n.id !== noteId)
    ElMessage.success("笔记已删除")
  } catch {
    ElMessage.error("删除失败")
  }
}

function goToJudge(name: string) {
  if (name) router.push(`/profile/judge/${encodeURIComponent(name)}`)
}

function goToRelated(caseId: number) {
  router.push(`/case/${caseId}`)
}

function scrollToSection(title: string) {
  activeSection.value = title
  const el = document.getElementById("section-" + title)
  if (el) el.scrollIntoView({ behavior: "smooth" })
}

function copyShareCard() {
  const text = `【律镜】${caseData.value?.title || caseData.value?.case_no}\n`
    + `法院：${caseData.value?.court || "未知"}\n`
    + `案号：${caseData.value?.case_no || ""}\n`
    + `裁判要旨：${caseData.value?.ruling_abstract || caseData.value?.summary || "暂无"}\n`
    + `—— 来自律镜 LawMirror (AI驱动的智能类案检索平台)`
  window.navigator.clipboard.writeText(text).then(() => ElMessage.success("分享卡片已复制到剪贴板"))
  showShareCard.value = false
}

function copyRule(text: string) {
  window.navigator.clipboard.writeText(text).then(() => ElMessage.success("已复制"))
}

// 拖拽分隔条
function onDividerMouseDown(e: MouseEvent) {
  const startX = e.clientX
  const startRatio = leftRatio.value
  const onMove = (ev: MouseEvent) => {
    const container = (e.target as HTMLElement).closest(".reader-container") as HTMLElement
    if (!container) return
    const dx = ev.clientX - startX
    const w = container.offsetWidth
    leftRatio.value = Math.min(75, Math.max(25, startRatio + (dx / w) * 100))
  }
  const onUp = () => {
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
  }
  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}

const levelLabels: Record<string, string> = {
  supreme: "最高人民法院", high: "高级人民法院", intermediate: "中级人民法院", basic: "基层人民法院",
}
const procedureLabels: Record<string, string> = {
  first: "一审", second: "二审", retrial: "再审", supervision: "审判监督",
}
</script>

<template>
  <!-- Loading -->
  <div v-if="loading" style="text-align: center; padding: 100px">
    <el-icon class="is-loading" :size="36" color="#3b82f6"><Loading /></el-icon>
    <p style="color: #94a3b8; margin-top: 12px">加载案例中...</p>
  </div>

  <div v-else-if="caseData" class="reader-page">
    <!-- ====== 顶部工具栏 ====== -->
    <div class="reader-toolbar">
      <div class="toolbar-left">
        <el-button :icon="ArrowLeft" size="small" @click="router.back()">返回</el-button>
        <h3>{{ caseData.title || caseData.case_no }}</h3>
      </div>
      <div class="toolbar-right">
        <el-button-group size="small">
          <el-button :icon="View" @click="fontSize = Math.max(12, fontSize - 2)" :disabled="fontSize <= 12" />
          <span class="font-size-label">{{ fontSize }}px</span>
          <el-button :icon="View" @click="fontSize = Math.min(24, fontSize + 2)" :disabled="fontSize >= 24" />
        </el-button-group>
        <el-button size="small" :icon="Notebook" @click="toggleNotes">
          {{ showNoteInput ? '收起笔记' : '笔记' }}
        </el-button>
        <el-button size="small" :icon="Switch" :type="caseData && basket.hasCase(caseData.id) ? 'success' : 'default'" @click="toggleCompare">
          {{ caseData && basket.hasCase(caseData.id) ? '已加入对比' : '加入对比' }}
        </el-button>
        <el-button size="small" :icon="Star" :type="isFavorite ? 'warning' : 'default'" @click="toggleFavorite">
          {{ isFavorite ? (favoriteGroupId ? '已收藏(已分组)' : '已收藏') : '收藏' }}
        </el-button>
        <el-button size="small" :icon="Share" @click="showShareCard = !showShareCard">分享</el-button>
        <el-button
          v-if="auth.isAdmin && caseData?.processing_status === 'completed'"
          size="small" type="danger" plain
          @click="unpublishCase"
        >下架</el-button>
        <el-tag v-if="caseData?.processing_status === 'unpublished'" type="danger" size="small">已下架</el-tag>
      </div>
    </div>

    <!-- ====== 分享卡片弹窗 ====== -->
    <el-dialog v-model="showShareCard" title="分享案例" width="480px">
      <div style="background:var(--bg-input);padding:20px;border-radius:8px;font-size:14px;line-height:1.8">
        <p style="color:var(--text-primary)"><b>{{ caseData.title || caseData.case_no }}</b></p>
        <p style="color:var(--text-tertiary)">法院：{{ caseData.court || '未知' }} | 案号：{{ caseData.case_no }}</p>
        <p style="color:var(--text-secondary);margin-top:8px">📋 {{ caseData.ruling_abstract || caseData.summary || '暂无裁判要旨' }}</p>
      </div>
      <template #footer>
        <el-button @click="showShareCard = false">关闭</el-button>
        <el-button type="primary" @click="copyShareCard">复制分享卡片</el-button>
      </template>
    </el-dialog>

    <!-- ====== 收藏分组弹窗 ====== -->
    <el-dialog v-model="showFavDialog" title="收藏案例" width="440px">
      <p style="color:var(--text-tertiary);margin-bottom:16px;font-size:13px">
        案例已加入收藏。选择一个分组进行分类整理（可选）：
      </p>
      <el-select
        v-model="selectedGroupId"
        placeholder="不分组（仅收藏）"
        clearable
        style="width: 100%"
      >
        <el-option
          v-for="g in groups"
          :key="g.id"
          :label="g.name + ' (' + (g.item_count || 0) + '个案例)'"
          :value="g.id"
        />
      </el-select>

      <!-- 新建分组 -->
      <div v-if="!showNewGroupInput" style="margin-top: 10px">
        <el-button size="small" text type="primary" @click="showNewGroupInput = true">
          ＋ 创建新分组
        </el-button>
      </div>
      <div v-else style="margin-top: 12px; padding: 12px; background: var(--bg-input); border-radius: 8px">
        <el-input
          v-model="newGroupName"
          placeholder="分组名称（必填）"
          size="small"
          style="margin-bottom: 8px"
          :disabled="creatingGroup"
        />
        <el-input
          v-model="newGroupDesc"
          placeholder="分组描述（可选）"
          size="small"
          :disabled="creatingGroup"
        />
        <div style="margin-top: 8px; display: flex; gap: 8px; justify-content: flex-end">
          <el-button size="small" @click="showNewGroupInput = false" :disabled="creatingGroup">取消</el-button>
          <el-button size="small" type="primary" :loading="creatingGroup" @click="createGroupAndSelect">
            创建并选中
          </el-button>
        </div>
      </div>

      <p style="color:var(--text-tertiary);font-size:12px;margin-top:8px">
        💡 收藏的案例会出现在工作台「收藏案例」中，加入分组后也会在「案例分组」中显示
      </p>
      <template #footer>
        <el-button @click="showFavDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmFavorite">
          {{ selectedGroupId ? '收藏并加入分组' : '确认收藏' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ====== 双栏布局 ====== -->
    <div class="reader-container">
      <!-- 左栏：原文 -->
      <div class="left-pane" :style="{ width: leftRatio + '%', fontSize: fontSize + 'px' }">
        <el-card shadow="never">
          <!-- 段落目录 -->
          <div class="section-nav">
            <div
              v-for="sec in sections" :key="sec.title"
              class="section-nav-item"
              :class="{ active: activeSection === sec.title }"
              @click="scrollToSection(sec.title)"
            >
              {{ sec.title }}
            </div>
          </div>

          <!-- 段落内容 -->
          <div class="full-text">
            <div
              v-for="sec in sections" :key="sec.title"
              :id="'section-' + sec.title"
              class="text-section"
            >
              <h4 class="section-title">{{ sec.title }}</h4>
              <p class="section-body">{{ sec.content || '（无内容）' }}</p>
            </div>
          </div>
        </el-card>
      </div>

      <!-- 分隔条 -->
      <div class="divider-bar" @mousedown="onDividerMouseDown">
        <div class="divider-handle" />
      </div>

      <!-- 右栏：AI 提炼 -->
      <div class="right-pane" :style="{ width: (100 - leftRatio) + '%' }">
        <!-- 案情概要 -->
        <el-card shadow="never" class="info-card">
          <h4>
            📋 案情概要
            <el-tag v-if="caseData.processing_status === 'pending'" type="info" size="small" style="margin-left:8px">待审核</el-tag>
            <el-tag v-else-if="caseData.processing_status && caseData.processing_status !== 'completed'" type="warning" size="small" style="margin-left:8px">处理中</el-tag>
          </h4>
          <p v-if="caseData.summary || caseData.ruling_abstract">
            {{ caseData.summary || caseData.ruling_abstract }}
          </p>
          <div v-else class="raw-preview">
            {{ (caseData.full_text || '').slice(0, 500) }}{{ (caseData.full_text || '').length > 500 ? '...' : '' }}
          </div>
        </el-card>

        <!-- 争议焦点 -->
        <el-card v-if="caseData.dispute_focuses?.length" shadow="never" class="info-card">
          <h4>⚡ 争议焦点 ({{ caseData.dispute_focuses.length }})</h4>
          <el-collapse>
            <el-collapse-item
              v-for="(f, i) in caseData.dispute_focuses" :key="i"
              :title="'焦点' + (Number(i) + 1) + '：' + f.focus_name"
            >
              <div class="focus-detail">
                <p><b>原告主张：</b>{{ f.plaintiff_claim || '-' }}</p>
                <p><b>被告抗辩：</b>{{ f.defendant_defense || '-' }}</p>
                <p><b>法院认定：</b>{{ f.court_finding || '-' }}</p>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>

        <!-- 裁判规则 -->
        <el-card v-if="caseData.legal_rules?.length" shadow="never" class="info-card">
          <h4>📜 裁判规则 ({{ caseData.legal_rules.length }})</h4>
          <div
            v-for="r in caseData.legal_rules" :key="r.id"
            class="rule-item"
            @click="copyRule(r.rule_text)"
          >
            <span class="rule-type-tag">{{ r.rule_type === 'establish' ? '确立' : r.rule_type === 'extend' ? '扩展' : r.rule_type === 'restrict' ? '限制' : r.rule_type === 'conflict' ? '冲突' : r.rule_type || '其他' }}</span>
            {{ r.rule_text }}
          </div>
        </el-card>

        <!-- 援引法条 -->
        <el-card v-if="caseData.articles?.length" shadow="never" class="info-card">
          <h4>📖 援引法条</h4>
          <el-tag v-for="a in caseData.articles" :key="a" style="margin: 4px" type="info">{{ a }}</el-tag>
        </el-card>

        <!-- 案件信息 -->
        <el-card shadow="never" class="info-card">
          <h4>📝 案件信息</h4>
          <div class="case-meta-list">
            <div class="meta-row"><span class="meta-label">案号</span><span>{{ caseData.case_no }}</span></div>
            <div class="meta-row"><span class="meta-label">法院</span><span>{{ caseData.court }}</span></div>
            <div class="meta-row"><span class="meta-label">层级</span><span>{{ levelLabels[caseData.court_level] || caseData.court_level || '-' }}</span></div>
            <div class="meta-row">
              <span class="meta-label">法官</span>
              <el-link type="primary" :underline="false" @click="goToJudge(caseData.judge_name)" v-if="caseData.judge_name">
                {{ caseData.judge_name }}
              </el-link>
              <span v-else>-</span>
            </div>
            <div class="meta-row"><span class="meta-label">程序</span><span>{{ procedureLabels[caseData.trial_procedure] || caseData.trial_procedure || '-' }}</span></div>
            <div class="meta-row"><span class="meta-label">日期</span><span>{{ caseData.judgment_date || '-' }}</span></div>
            <div class="meta-row"><span class="meta-label">案由</span><span>{{ caseData.case_category_2 || caseData.case_category_1 || '-' }}</span></div>
            <div class="meta-row"><span class="meta-label">标签</span>
              <span v-if="caseData.tags?.length">
                <el-tag v-for="t in caseData.tags" :key="t" size="small" style="margin:2px">{{ t }}</el-tag>
              </span>
              <span v-else>-</span>
            </div>
          </div>
        </el-card>

        <!-- 我的笔记 -->
        <el-card v-if="showNoteInput" ref="notesSection" shadow="never" class="info-card">
          <h4>📒 我的笔记</h4>
          <div v-if="notes.length" style="margin-bottom: 12px">
            <div v-for="n in notes" :key="n.id" style="padding:8px;background:var(--bg-input);border-radius:6px;margin-bottom:6px;font-size:13px">
              <!-- 查看 / 编辑模式 -->
              <template v-if="editingNoteId === n.id">
                <el-input
                  v-model="editingNoteText"
                  type="textarea"
                  :rows="3"
                  size="small"
                  style="margin-bottom:6px"
                />
                <div style="display:flex;gap:6px;justify-content:flex-end">
                  <button class="acct-tab-btn" @click="cancelEdit">取消</button>
                  <button class="acct-tab-btn" :disabled="!editingNoteText.trim()" @click="saveEditNote(n.id)">保存</button>
                </div>
              </template>
              <template v-else>
                <span style="white-space:pre-wrap;word-break:break-word">{{ n.content }}</span>
                <span v-if="n.paragraph_ref" style="color:var(--text-tertiary);font-size:11px;display:block;margin-top:4px">—— 引用自「{{ n.paragraph_ref }}」</span>
                <div style="margin-top:6px;display:flex;align-items:center;gap:8px">
                  <button class="acct-tab-btn" @click="startEditNote(n)">修改</button>
                  <button class="user-del-btn" title="删除笔记" @click="deleteNote(n.id)">
                    <svg class="trash-svg" viewBox="0 -10 64 74" xmlns="http://www.w3.org/2000/svg">
                      <g><rect x="16" y="24" width="32" height="30" rx="3" ry="3" fill="#e74c3c"/><g transform-origin="12 18" id="lid-group"><rect x="12" y="12" width="40" height="6" rx="2" ry="2" fill="#c0392b"/><rect x="26" y="8" width="12" height="4" rx="2" ry="2" fill="#c0392b"/></g></g>
                    </svg>
                  </button>
                </div>
              </template>
            </div>
          </div>
          <el-input v-model="noteText" type="textarea" :rows="3" placeholder="在此记录你的办案心得..." />
          <el-button type="primary" size="small" style="margin-top: 8px" @click="addNote" :disabled="!noteText.trim()">保存笔记</el-button>
        </el-card>

        <!-- 关联案例 -->
        <el-card v-if="related.length" shadow="never" class="info-card">
          <h4>🔗 关联案例 ({{ related.length }})</h4>
          <div
            v-for="r in related" :key="r.id"
            class="related-item"
            @click="goToRelated(r.id)"
          >
            <div class="related-title">{{ r.title || r.case_no }}</div>
            <div class="related-meta">
              <el-tag size="small" :type="r.relation_type === 'conflict' ? 'danger' : 'info'">
                {{ r.relation_type === 'similar' ? '类案' : r.relation_type === 'conflict' ? '观点冲突' : r.relation_type === 'cite' ? '引用' : r.relation_type === 'inherit' ? '承继' : r.relation_type === 'same_category' ? '同案由' : r.relation_type }}
              </el-tag>
              <span>{{ r.court }}</span>
            </div>
            <p v-if="r.relation_detail" style="font-size:12px;color:var(--text-tertiary);margin-top:4px">{{ r.relation_detail }}</p>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reader-page { max-width: 1500px; margin: 0 auto; animation: fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) both; }

/* Toolbar */
.reader-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0 0 16px; border-bottom: 1px solid var(--ring-color); margin-bottom: 18px;
}
.toolbar-left { display: flex; align-items: center; gap: 14px; }
.toolbar-left h3 { font-size: 17px; color: var(--text-primary); max-width: 500px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 700; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.font-size-label { font-size: 12px; color: var(--text-tertiary); min-width: 36px; text-align: center; }

/* Dual pane */
.reader-container { display: flex; gap: 0; align-items: flex-start; }
.left-pane { min-width: 280px; }
.right-pane { min-width: 300px; display: flex; flex-direction: column; gap: 14px; }

.divider-bar {
  width: 10px; min-width: 10px; cursor: col-resize;
  display: flex; align-items: center; justify-content: center;
  align-self: stretch; min-height: 400px;
}
.divider-bar:hover .divider-handle { background: var(--accent-blue); }
.divider-handle {
  width: 4px; height: 60px; background: var(--text-muted); border-radius: 3px; transition: background 0.2s;
}

/* Section nav */
.section-nav { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--ring-color); }
.section-nav-item {
  font-size: 12px; padding: 5px 12px; border-radius: 20px; cursor: pointer; font-weight: 500;
  background: var(--bg-input); color: var(--text-tertiary); transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1); white-space: nowrap;
  box-shadow: 0 0 0 1px var(--ring-color);
}
.section-nav-item:hover { background: var(--bg-hover); color: var(--text-primary); transform: scale(1.03); }
.section-nav-item.active { background: var(--accent-blue); color: #fff; box-shadow: none; }

/* Full text */
.full-text { max-height: 70vh; overflow-y: auto; padding-right: 8px; }
.text-section { margin-bottom: 24px; }
.section-title { font-size: 15px; color: var(--text-primary); margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid var(--ring-color); font-weight: 600; }
.section-body { font-size: inherit; line-height: 2; color: var(--text-secondary); white-space: pre-wrap; }

/* Info cards */
.info-card h4 { font-size: 15px; color: var(--text-primary); margin-bottom: 12px; font-weight: 600; }
.info-card p { font-size: 13px; color: var(--text-secondary); line-height: 1.7; }
.raw-preview {
  font-size: 13px; color: var(--text-tertiary); line-height: 1.7;
  white-space: pre-wrap; max-height: 200px; overflow-y: auto;
  background: var(--bg-input); padding: 12px; border-radius: 10px;
  box-shadow: 0 0 0 1px var(--ring-color);
}

.focus-detail p { font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; line-height: 1.6; }

.rule-item {
  padding: 10px 12px; background: rgba(13, 107, 74, 0.04); border-radius: 10px; margin-bottom: 6px;
  font-size: 13px; line-height: 1.6; cursor: pointer; transition: all 0.2s; color: var(--text-secondary);
  box-shadow: 0 0 0 1px rgba(13, 107, 74, 0.15);
}
.rule-item:hover { background: rgba(13, 107, 74, 0.08); transform: translateX(2px); }
.rule-type-tag { font-size: 11px; background: var(--accent-green); color: #fff; padding: 2px 8px; border-radius: 6px; margin-right: 6px; font-weight: 600; }

.case-meta-list { font-size: 13px; }
.meta-row { display: flex; padding: 7px 0; border-bottom: 1px solid var(--ring-color); }
.meta-row:last-child { border-bottom: none; }
.meta-label { width: 60px; color: var(--text-tertiary); flex-shrink: 0; }

.related-item {
  padding: 12px; background: var(--bg-input); border-radius: 10px; margin-bottom: 6px;
  cursor: pointer; transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
  box-shadow: 0 0 0 1px var(--ring-color);
}
.related-item:hover { background: #fff; transform: translateY(-1px); box-shadow: 0 2px 12px rgba(26, 39, 68, 0.06); }
.related-title { font-size: 13px; color: var(--accent-blue); font-weight: 600; }
.related-meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 12px; color: var(--text-tertiary); }

/* —— 修改按钮（与账号管理模态框一致） —— */
.acct-tab-btn {
  padding: 0.25em 0.7em; font-size: 11px; letter-spacing: 0.5px;
  font-weight: 500; color: #8B949E; background: transparent;
  border: 1px solid #30363D; border-radius: 6px; cursor: pointer;
  box-shadow: 0px 4px 10px rgba(0,0,0,0.15); transition: all 0.3s ease;
  outline: none; font-family: inherit;
}
.acct-tab-btn:hover {
  background: #1F1F1F; border-color: #30363D; color: #fff;
  box-shadow: 0px 12px 20px rgba(88,166,255,0.35); transform: translateY(-5px);
}
.acct-tab-btn:active { transform: translateY(-1px); }
.acct-tab-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; box-shadow: none; }

/* —— 删除按钮（与 Admin 用户管理一致） —— */
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
