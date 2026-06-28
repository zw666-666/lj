<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { useRouter } from "vue-router"
import api from "@/api/client"
import { useAuthStore } from "@/stores/auth"
import { Plus, Edit, FolderOpened, Notebook, ArrowDown, Download } from "@element-plus/icons-vue"
import CountUp from "@/components/common/CountUp.vue"
import { ElMessage, ElMessageBox } from "element-plus"
import UpgradePrompt from "@/components/common/UpgradePrompt.vue"

const router = useRouter()
const auth = useAuthStore()
const showUpgrade = ref(false)

const activeTab = ref("favorites")
const favorites = ref<any[]>([])
const groups = ref<any[]>([])
const notes = ref<any[]>([])
const stats = ref<any>({})
const expandedGroups = ref<Set<number>>(new Set())
const groupItems = ref<Map<number, any[]>>(new Map())

// 按案例分组笔记
const groupedNotes = computed(() => {
  const map = new Map<number, { case_id: number; case_title: string; case_no: string; notes: any[] }>()
  for (const n of notes.value) {
    const key = n.case_id
    if (!map.has(key)) {
      map.set(key, { case_id: key, case_title: n.case_title, case_no: n.case_no, notes: [] })
    }
    map.get(key)!.notes.push(n)
  }
  return [...map.values()]
})

// 历史记录弹窗
const showSearchHistory = ref(false)
const showReadHistory = ref(false)
const searchHistory = ref<any[]>([])
const readHistory = ref<any[]>([])
const loadingHistory = ref(false)

// 新建分组
const showNewGroup = ref(false)
const newGroupName = ref("")
const newGroupDesc = ref("")

// 标签编辑
const editingTag = ref<{ favId: number; tags: string } | null>(null)
const tagInput = ref("")

onMounted(async () => {
  try {
    const [favRes, groupRes, statsRes, notesRes] = await Promise.all([
      api.get("/workspace/favorites"),
      api.get("/workspace/groups"),
      api.get("/user/stats"),
      api.get("/workspace/notes"),
    ])
    favorites.value = favRes.data
    groups.value = groupRes.data
    stats.value = statsRes.data
    notes.value = Array.isArray(notesRes.data) ? notesRes.data : []
  } catch {}
})

async function loadNotes() {
  try {
    const res = await api.get("/workspace/notes/0") // TODO: get all notes
    notes.value = Array.isArray(res.data) ? res.data : []
  } catch {}
}

async function removeFavorite(caseId: number) {
  try {
    await api.delete(`/workspace/favorites/${caseId}`)
    favorites.value = favorites.value.filter(f => f.case_id !== caseId)
    stats.value.favorite_count = favorites.value.length
    ElMessage.success("已取消收藏")
  } catch {}
}

async function saveTags(fav: any) {
  try {
    const tags = tagInput.value.split(",").map(t => t.trim()).filter(Boolean)
    await api.put(`/workspace/favorites/${fav.case_id}`, { tags })
    fav.tags = tags
    editingTag.value = null
    ElMessage.success("标签已更新")
  } catch {}
}

async function createGroup() {
  if (!newGroupName.value.trim()) return
  try {
    await api.post("/workspace/groups", {
      name: newGroupName.value,
      description: newGroupDesc.value,
    })
    ElMessage.success("分组已创建")
    showNewGroup.value = false
    newGroupName.value = ""
    newGroupDesc.value = ""
    const res = await api.get("/workspace/groups")
    groups.value = res.data
    stats.value.favorite_count = favorites.value.length  // 确保收藏计数同步
  } catch {}
}

async function deleteGroup(groupId: number) {
  try {
    await ElMessageBox.confirm(
      "确定删除此分组？分组内的案例将不会被删除，仅取消分组关联。",
      "确认删除分组",
      { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" }
    )
    await api.delete(`/workspace/groups/${groupId}`)
    groups.value = groups.value.filter(g => g.id !== groupId)
    expandedGroups.value.delete(groupId)
    groupItems.value.delete(groupId)
    ElMessage.success("分组已删除")
  } catch (e: any) {
    if (e === 'cancel' || e === 'close') return  // 用户取消，不提示
    const detail = e?.response?.data?.detail
    ElMessage.error(detail || `删除失败（${e?.response?.status || e?.message || '未知错误'}）`)
  }
}

async function toggleGroupExpand(groupId: number) {
  if (expandedGroups.value.has(groupId)) {
    expandedGroups.value.delete(groupId)
  } else {
    expandedGroups.value.add(groupId)
    // 加载分组内案例
    if (!groupItems.value.has(groupId)) {
      try {
        const res = await api.get(`/workspace/groups/${groupId}/items`)
        groupItems.value.set(groupId, Array.isArray(res.data) ? res.data : [])
      } catch {
        groupItems.value.set(groupId, [])
      }
    }
  }
}

async function removeFromGroup(groupId: number, caseId: number) {
  try {
    await api.delete(`/workspace/groups/${groupId}/items/${caseId}`)
    const items = groupItems.value.get(groupId) || []
    groupItems.value.set(groupId, items.filter((i: any) => i.case_id !== caseId))
    // 更新 item_count
    const g = groups.value.find(gr => gr.id === groupId)
    if (g) g.item_count = Math.max(0, (g.item_count || 0) - 1)
    ElMessage.success("已从分组移除")
  } catch {
    ElMessage.error("操作失败")
  }
}

// 添加案例到分组（模态框）
const showAddCaseModal = ref(false)
const addingGroupId = ref<number | null>(null)
const addingGroupItems = ref<any[]>([])
const selectedCaseIds = ref<number[]>([])
const addingToGroup = ref(false)

async function openAddCaseModal(groupId: number) {
  addingGroupId.value = groupId
  selectedCaseIds.value = []
  showAddCaseModal.value = true
  addingToGroup.value = false
  // 确保分组内案例已加载（用于判断哪些已存在）
  if (!groupItems.value.has(groupId)) {
    try {
      const res = await api.get(`/workspace/groups/${groupId}/items`)
      groupItems.value.set(groupId, Array.isArray(res.data) ? res.data : [])
    } catch {
      groupItems.value.set(groupId, [])
    }
  }
  addingGroupItems.value = groupItems.value.get(groupId) || []
}

function isInCurrentGroup(caseId: number): boolean {
  return addingGroupItems.value.some((i: any) => i.case_id === caseId)
}

function toggleCaseSelect(caseId: number, val?: boolean) {
  const exists = selectedCaseIds.value.includes(caseId)
  if (val === true || (val === undefined && !exists)) {
    if (!exists) selectedCaseIds.value.push(caseId)
  } else {
    selectedCaseIds.value = selectedCaseIds.value.filter(id => id !== caseId)
  }
}

async function confirmAddCases() {
  if (!addingGroupId.value || !selectedCaseIds.value.length) {
    ElMessage.warning("请至少选择一个案例")
    return
  }
  addingToGroup.value = true
  const gid = addingGroupId.value
  let successCount = 0
  let failCount = 0
  for (const cid of selectedCaseIds.value) {
    try {
      await api.post(`/workspace/groups/${gid}/items/${cid}`)
      successCount++
    } catch {
      failCount++
    }
  }
  // 刷新分组内案例列表
  try {
    const res = await api.get(`/workspace/groups/${gid}/items`)
    groupItems.value.set(gid, Array.isArray(res.data) ? res.data : [])
    const g = groups.value.find(gr => gr.id === gid)
    if (g) g.item_count = (Array.isArray(res.data) ? res.data : []).length
  } catch {}
  showAddCaseModal.value = false
  selectedCaseIds.value = []
  if (successCount && !failCount) {
    ElMessage.success(`已添加 ${successCount} 个案例到分组`)
  } else if (successCount && failCount) {
    ElMessage.warning(`成功 ${successCount} 个，失败 ${failCount} 个`)
  } else {
    ElMessage.error("添加失败")
  }
  addingToGroup.value = false
}

async function loadSearchHistory() {
  loadingHistory.value = true
  showSearchHistory.value = true
  try {
    const res = await api.get("/user/search-history", { params: { limit: 50 } })
    searchHistory.value = res.data
  } catch {
    searchHistory.value = []
  } finally {
    loadingHistory.value = false
  }
}

async function loadReadHistory() {
  loadingHistory.value = true
  showReadHistory.value = true
  try {
    const res = await api.get("/user/read-history", { params: { limit: 50 } })
    readHistory.value = res.data
  } catch {
    readHistory.value = []
  } finally {
    loadingHistory.value = false
  }
}

function goToCaseFromHistory(caseId: number) {
  showReadHistory.value = false
  router.push("/case/" + caseId)
}

async function handleExport(caseId: number) {
  try {
    const res = await api.post(`/workspace/export/case/${caseId}`, {}, { responseType: "blob" })
    const blob = new Blob([res.data], { type: "text/plain;charset=utf-8" })
    const a = document.createElement("a")
    a.href = URL.createObjectURL(blob)
    a.download = `律镜_案例报告_${caseId}.txt`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success("报告已导出")
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

const exportRemainingText = computed(() => {
  if (auth.isPremium) return ""
  return `(剩余${auth.exportRemaining}次)`
})
</script>

<template>
  <div style="max-width: 1000px; margin: 0 auto">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h3 style="color:var(--text-primary)">个人工作台</h3>
      <span style="color:var(--text-tertiary);font-size:13px">{{ auth.user?.nickname || '用户' }} · {{ auth.user?.role === 'admin' ? '管理员' : '用户' }}</span>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" style="margin-bottom:24px">
      <el-col :span="6">
        <el-card shadow="hover" class="mini-stat clickable" @click="loadSearchHistory">
          <div class="mini-stat-num"><CountUp :to="stats.search_count || 0" /></div>
          <div class="mini-stat-label">检索次数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="mini-stat clickable" @click="loadReadHistory">
          <div class="mini-stat-num"><CountUp :to="stats.read_count || 0" /></div>
          <div class="mini-stat-label">阅读案例</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="mini-stat" @click="activeTab = 'favorites'">
          <div class="mini-stat-num"><CountUp :to="favorites.length" /></div>
          <div class="mini-stat-label">收藏案例</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="mini-stat" @click="activeTab = 'notes'">
          <div class="mini-stat-num"><CountUp :to="notes.length" /></div>
          <div class="mini-stat-label">笔记数</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 检索历史弹窗 -->
    <el-dialog v-model="showSearchHistory" title="检索历史" width="580px">
      <div v-if="loadingHistory" style="text-align:center;padding:20px">加载中...</div>
      <div v-else-if="!searchHistory.length" style="text-align:center;padding:20px;color:var(--text-tertiary)">暂无检索记录</div>
      <div v-else>
        <div
          v-for="(item, i) in searchHistory" :key="item.id"
          style="padding:10px 0;border-bottom:1px solid var(--border-color)"
        >
          <div style="display:flex;align-items:center;gap:8px">
            <span style="color:var(--text-tertiary);font-size:12px;min-width:28px">{{ i + 1 }}</span>
            <span style="flex:1;color:var(--text-secondary);font-size:13px;font-weight:500">{{ item.detail }}</span>
            <span style="color:var(--text-tertiary);font-size:11px;white-space:nowrap">{{ item.created_at?.slice(0, 16)?.replace('T', ' ') }}</span>
          </div>
          <!-- 检索到的案件列表 -->
          <div v-if="item.result_data?.cases?.length" style="margin-top:6px;margin-left:36px;display:flex;flex-direction:column;gap:2px">
            <div
              v-for="c in item.result_data.cases" :key="c.id"
              style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--accent-blue);cursor:pointer;padding:2px 0"
              @click="router.push('/case/' + c.id)"
              :title="c.title"
            >
              <span style="width:4px;height:4px;border-radius:50%;background:var(--accent-blue);flex-shrink:0"></span>
              <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ c.title }}</span>
              <span v-if="c.case_no" style="color:var(--text-tertiary)">({{ c.case_no }})</span>
            </div>
            <span v-if="item.result_data.total > 5" style="font-size:11px;color:var(--text-tertiary);margin-left:10px">...共 {{ item.result_data.total }} 条结果</span>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 阅读历史弹窗 -->
    <el-dialog v-model="showReadHistory" title="阅读历史" width="550px">
      <div v-if="loadingHistory" style="text-align:center;padding:20px">加载中...</div>
      <div v-else-if="!readHistory.length" style="text-align:center;padding:20px;color:var(--text-tertiary)">暂无阅读记录</div>
      <div v-else>
        <div
          v-for="(item, i) in readHistory" :key="item.id"
          style="display:flex;align-items:center;padding:10px 0;border-bottom:1px solid var(--border-color);cursor:pointer"
          @click="goToCaseFromHistory(item.case_id)"
          class="read-history-item"
        >
          <span style="color:var(--text-tertiary);font-size:12px;min-width:28px">{{ i + 1 }}</span>
          <div style="flex:1;min-width:0">
            <div style="color:var(--accent-blue);font-size:13px;font-weight:500">{{ item.title }}</div>
            <div v-if="item.case_no" style="color:var(--text-tertiary);font-size:11px">{{ item.case_no }}</div>
          </div>
          <span style="color:var(--text-tertiary);font-size:11px;white-space:nowrap">{{ item.created_at?.slice(0, 16)?.replace('T', ' ') }}</span>
        </div>
      </div>
    </el-dialog>

    <el-tabs v-model="activeTab">
      <!-- 收藏标签页 -->
      <el-tab-pane label="收藏案例" name="favorites">
        <div v-if="favorites.length">
          <el-card v-for="fav in favorites" :key="fav.id" shadow="hover" class="fav-card">
            <div class="fav-main">
              <div class="fav-info">
                <span class="fav-link" @click="router.push('/case/' + fav.case_id)">
                  {{ fav.title || fav.case_no || '案例 #' + fav.case_id }}
                </span>
                <span v-if="fav.case_no" style="color:var(--text-tertiary);font-size:12px;margin-left:8px">{{ fav.case_no }}</span>
                <div class="fav-tags">
                  <el-tag
                    v-for="tag in (fav.tags || [])"
                    :key="tag" size="small" style="margin:2px"
                    @click="editingTag = { favId: fav.id, tags: (fav.tags || []).join(',') }; tagInput = (fav.tags || []).join(',')"
                  >
                    {{ tag }}
                  </el-tag>
                </div>
              </div>
              <div class="fav-actions">
                <el-button size="small" text @click="handleExport(fav.case_id)" :title="auth.isPremium ? '导出报告' : `导出报告 ${exportRemainingText}`">
                  <el-icon><Download /></el-icon> 导出
                </el-button>
                <el-button size="small" text @click="editingTag = { favId: fav.id, tags: (fav.tags || []).join(',') }; tagInput = (fav.tags || []).join(',')">
                  <el-icon><Edit /></el-icon> 标签
                </el-button>
                <button class="user-del-btn" title="移除收藏" @click="removeFavorite(fav.case_id)">
                  <svg class="trash-svg" viewBox="0 -10 64 74" xmlns="http://www.w3.org/2000/svg">
                    <g><rect x="16" y="24" width="32" height="30" rx="3" ry="3" fill="#e74c3c"/><g transform-origin="12 18" id="lid-group"><rect x="12" y="12" width="40" height="6" rx="2" ry="2" fill="#c0392b"/><rect x="26" y="8" width="12" height="4" rx="2" ry="2" fill="#c0392b"/></g></g>
                  </svg>
                </button>
              </div>
            </div>
            <!-- 标签编辑 -->
            <div v-if="editingTag?.favId === fav.id" style="margin-top:8px;display:flex;gap:8px;align-items:center">
              <el-input v-model="tagInput" size="small" placeholder="标签（逗号分隔），如：对我方有利, 二审改判参考" style="flex:1" />
              <button class="fav-tag-save-btn" @click="saveTags(fav)">保存</button>
              <button class="fav-tag-cancel-btn" @click="editingTag = null">取消</button>
            </div>
          </el-card>
        </div>
        <el-empty v-else description="还没有收藏案例，在检索结果或案例详情页点击收藏">
          <el-button type="primary" @click="router.push('/home')">去搜索案例</el-button>
        </el-empty>
      </el-tab-pane>

      <!-- 案例分组标签页 -->
      <el-tab-pane label="案例分组" name="groups">
        <div style="margin-bottom:12px">
          <el-button :icon="Plus" size="small" @click="showNewGroup = !showNewGroup">
            {{ showNewGroup ? '取消' : '新建分组' }}
          </el-button>
        </div>
        <div v-if="showNewGroup" style="margin-bottom:16px;display:flex;gap:8px">
          <el-input v-model="newGroupName" placeholder="分组名称" size="small" style="width:200px" />
          <el-input v-model="newGroupDesc" placeholder="描述（可选）" size="small" style="width:300px" />
          <el-button size="small" type="primary" @click="createGroup">创建</el-button>
        </div>
        <div v-if="groups.length" style="display:flex;flex-direction:column;gap:8px">
          <el-card
            v-for="g in groups" :key="g.id"
            shadow="hover"
            class="group-card"
          >
            <!-- 分组头部 -->
            <div class="group-header" @click="toggleGroupExpand(g.id)">
              <div style="flex:1">
                <div style="display:flex;align-items:center;gap:8px">
                  <el-icon :size="16" color="#2563eb"><FolderOpened /></el-icon>
                  <h5 style="color:var(--text-primary);margin:0">{{ g.name }}</h5>
                  <el-tag size="small">{{ g.item_count || 0 }} 个案例</el-tag>
                  <el-icon
                    style="transition:transform 0.2s;margin-left:auto"
                    :style="{ transform: expandedGroups.has(g.id) ? 'rotate(90deg)' : '' }"
                  >
                    <ArrowDown />
                  </el-icon>
                </div>
                <p v-if="g.description" style="color:var(--text-muted);font-size:13px;margin:4px 0 0 24px">{{ g.description }}</p>
              </div>
              <el-button
                size="small"
                text
                :icon="Plus"
                @click.stop="openAddCaseModal(g.id)"
                style="margin-left:12px"
                title="添加案例到分组"
              />
              <button class="user-del-btn" style="margin-left:4px" title="删除分组" @click.stop="deleteGroup(g.id)">
                <svg class="trash-svg" viewBox="0 -10 64 74" xmlns="http://www.w3.org/2000/svg">
                  <g><rect x="16" y="24" width="32" height="30" rx="3" ry="3" fill="#e74c3c"/><g transform-origin="12 18" id="lid-group"><rect x="12" y="12" width="40" height="6" rx="2" ry="2" fill="#c0392b"/><rect x="26" y="8" width="12" height="4" rx="2" ry="2" fill="#c0392b"/></g></g>
                </svg>
              </button>
            </div>

            <!-- 分组内案例列表 -->
            <div v-if="expandedGroups.has(g.id)" class="group-items" @click.stop>
              <div v-if="!groupItems.has(g.id)" style="text-align:center;padding:12px;color:var(--text-tertiary)">
                加载中...
              </div>
              <div v-else-if="!groupItems.get(g.id)!.length" style="text-align:center;padding:12px;color:var(--text-tertiary)">
                此分组还没有案例，在案例详情页收藏时选择此分组即可添加
              </div>
              <div
                v-for="item in groupItems.get(g.id)"
                :key="item.id"
                class="group-item-row"
              >
                <div class="group-item-info">
                  <span class="group-item-link" @click="router.push('/case/' + item.case_id)">
                    {{ item.title || item.case_no }}
                  </span>
                  <span style="color:var(--text-tertiary);font-size:12px;margin-left:8px">{{ item.case_no }}</span>
                  <span v-if="item.court" style="color:var(--text-tertiary);font-size:12px;margin-left:8px">{{ item.court }}</span>
                </div>
                <button class="user-del-btn" title="移出分组" @click="removeFromGroup(g.id, item.case_id)">
                  <svg class="trash-svg" viewBox="0 -10 64 74" xmlns="http://www.w3.org/2000/svg">
                    <g><rect x="16" y="24" width="32" height="30" rx="3" ry="3" fill="#e74c3c"/><g transform-origin="12 18" id="lid-group"><rect x="12" y="12" width="40" height="6" rx="2" ry="2" fill="#c0392b"/><rect x="26" y="8" width="12" height="4" rx="2" ry="2" fill="#c0392b"/></g></g>
                  </svg>
                </button>
              </div>
            </div>
          </el-card>
        </div>
        <el-empty v-if="!showNewGroup && !groups.length" description="创建分组来整理你的案例（如：张三诉李四案-参考资料）" />
      </el-tab-pane>

      <!-- 我的笔记标签页 -->
      <el-tab-pane label="我的笔记" name="notes">
        <div v-if="notes.length">
          <el-card v-for="group in groupedNotes" :key="group.case_id" shadow="hover" style="margin-bottom:12px">
            <!-- 案例头部 -->
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--border-color)">
              <el-link type="primary" @click="router.push('/case/' + group.case_id + '?showNotes=1')" :underline="false" style="font-size:14px;font-weight:600">
                {{ group.case_title || group.case_no }}
              </el-link>
              <span v-if="group.case_no" style="color:var(--text-tertiary);font-size:12px">{{ group.case_no }}</span>
              <el-tag size="small" style="margin-left:auto">{{ group.notes.length }} 条笔记</el-tag>
            </div>
            <!-- 该案例的所有笔记 -->
            <div v-for="(n, i) in group.notes" :key="n.id"
              style="padding:8px 12px;border-radius:6px;margin-bottom:6px"
              :style="{ background: i % 2 === 0 ? 'var(--bg-input)' : 'transparent' }"
            >
              <p style="color:var(--text-secondary);font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-word;margin:0">{{ n.content }}</p>
              <div style="display:flex;gap:16px;margin-top:4px;font-size:11px;color:var(--text-tertiary)">
                <span v-if="n.paragraph_ref">📌 引用自「{{ n.paragraph_ref }}」</span>
                <span>{{ n.created_at?.slice(0, 10) }}</span>
              </div>
            </div>
          </el-card>
        </div>
        <el-empty v-else description="还没有笔记，在案例详情页阅读时记录你的办案心得">
          <el-button type="primary" @click="router.push('/home')">去搜索案例</el-button>
        </el-empty>
      </el-tab-pane>
    </el-tabs>

    <!-- 升级引导 -->
    <UpgradePrompt
      v-model:visible="showUpgrade"
      feature-name="案例报告导出"
      description="免费用户只能导出2次报告，升级会员即可无限导出。"
    />

    <!-- 添加案例到分组模态框 -->
    <el-dialog
      v-model="showAddCaseModal"
      title="添加案例到分组"
      width="560px"
      :close-on-click-modal="false"
    >
      <div v-if="!favorites.length" style="text-align:center;padding:24px;color:var(--text-tertiary)">
        暂无收藏案例，请先在案例详情页收藏
      </div>
      <div v-else class="add-case-list">
        <div
          v-for="fav in favorites"
          :key="fav.case_id"
          class="add-case-row"
          :class="{ disabled: isInCurrentGroup(fav.case_id) }"
          @click="!isInCurrentGroup(fav.case_id) && toggleCaseSelect(fav.case_id)"
        >
          <div class="cntr">
            <input
              type="checkbox"
              class="hidden-xs-up"
              :checked="selectedCaseIds.includes(fav.case_id)"
              :disabled="isInCurrentGroup(fav.case_id)"
              @click.stop
              @change="(e) => toggleCaseSelect(fav.case_id, (e.target as HTMLInputElement).checked)"
            />
            <label class="cbx" :class="{ checked: selectedCaseIds.includes(fav.case_id), disabled: isInCurrentGroup(fav.case_id) }" @click.prevent.stop="!isInCurrentGroup(fav.case_id) && toggleCaseSelect(fav.case_id)"></label>
          </div>
          <div class="add-case-info">
            <span class="add-case-title">{{ fav.title || fav.case_no }}</span>
            <span class="add-case-meta">{{ fav.case_no }}</span>
            <span v-if="fav.court" class="add-case-meta">{{ fav.court }}</span>
            <el-tag v-if="isInCurrentGroup(fav.case_id)" size="small" type="info" style="margin-left:8px">已在分组</el-tag>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showAddCaseModal = false">取消</el-button>
        <el-button type="primary" :loading="addingToGroup" @click="confirmAddCases">
          添加 ({{ selectedCaseIds.length }})
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mini-stat {
  text-align: center;
  padding: 16px;
  border-radius: var(--radius-lg);
  box-shadow: 0 0 0 1px var(--ring-color);
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}
.mini-stat.clickable { cursor: pointer; }
.mini-stat.clickable:hover {
  box-shadow: 0 0 0 1px var(--accent-blue), 0 4px 16px rgba(26, 39, 68, 0.06);
  transform: translateY(-2px);
}
.mini-stat-num { font-size: 28px; font-weight: 700; color: var(--text-primary); }
.mini-stat-label { font-size: 12px; color: var(--text-tertiary); font-weight: 500; }
.read-history-item:hover { background: var(--bg-hover); }
.fav-card { margin-bottom: 8px; }
.fav-main { display: flex; justify-content: space-between; align-items: center; }
.fav-link { color: var(--accent-blue); cursor: pointer; font-size: 14px; font-weight: 600; }
.fav-link:hover { text-decoration: underline; }
.fav-tags { margin-top: 4px; }
.fav-actions { display: flex; gap: 4px; }
.group-card {
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}
.group-card:hover {
  box-shadow: 0 0 0 1px var(--accent-blue), 0 4px 16px rgba(26, 39, 68, 0.06);
  transform: translateY(-1px);
}
.group-header { display: flex; align-items: flex-start; cursor: pointer; user-select: none; }
.group-items { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--ring-color); }
.group-item-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-radius: 8px; transition: background 0.15s;
}
.group-item-row:hover { background: var(--bg-hover); }
.group-item-info { display: flex; align-items: center; flex: 1; min-width: 0; }
.group-item-link {
  color: var(--accent-blue); font-size: 13px; font-weight: 500; cursor: pointer;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.group-item-link:hover { text-decoration: underline; }

.add-case-list { max-height: 420px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.add-case-row {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--ring-color); transition: background 0.2s;
}
.add-case-row:hover { background: var(--bg-hover); }
.add-case-row.disabled { opacity: 0.45; cursor: default; }
.add-case-row.disabled:hover { background: transparent; }
.add-case-info { display: flex; align-items: center; flex: 1; min-width: 0; flex-wrap: wrap; gap: 6px; }
.add-case-title {
  color: var(--text-primary); font-size: 13px; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px;
}
.add-case-meta { color: var(--text-tertiary); font-size: 12px; }

/* —— 自定义复选框 —— */
.cntr { position: relative; }
.hidden-xs-up { display: none !important; }
.cbx {
  position: relative;
  top: 1px;
  width: 18px;
  height: 18px;
  border: 1px solid #c8ccd4;
  border-radius: 3px;
  vertical-align: middle;
  transition: background 0.1s ease;
  cursor: pointer;
  display: block;
}
.cbx:after {
  content: '';
  position: absolute;
  top: 1px;
  left: 5px;
  width: 5px;
  height: 9px;
  opacity: 0;
  transform: rotate(45deg) scale(0);
  border-right: 1px solid #fff;
  border-bottom: 1px solid #fff;
  transition: all 0.3s ease;
  transition-delay: 0.15s;
}
.cbx.checked {
  border-color: transparent;
  background: #6871f1;
  animation: jelly 0.6s ease;
}
.cbx.checked:after {
  opacity: 1;
  transform: rotate(45deg) scale(1);
}
.cbx.disabled { opacity: 0.45; cursor: default; }
@keyframes jelly {
  from { transform: scale(1, 1); }
  30% { transform: scale(1.25, 0.75); }
  40% { transform: scale(0.75, 1.25); }
  50% { transform: scale(1.15, 0.85); }
  65% { transform: scale(0.95, 1.05); }
  75% { transform: scale(1.05, 0.95); }
  to { transform: scale(1, 1); }
}

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

/* 标签编辑 - 保存/取消按钮（与账号管理已保存账号按钮同款） */
.fav-tag-save-btn {
  position: relative; height: 26px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid #2F65FF; background: #2F65FF;
  border-radius: 6px; overflow: hidden; font-family: inherit; padding: 0 10px;
  color: #fff; font-weight: 600; font-size: 11px;
  transition: all 0.3s ease; white-space: nowrap;
}
.fav-tag-save-btn:hover { background: #1D4ED8; border-color: #1D4ED8; }
.fav-tag-save-btn:active { background: #1D4ED8; border-color: #1D4ED8; }

.fav-tag-cancel-btn {
  position: relative; height: 26px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid #30363D; background: #1F1F1F;
  border-radius: 6px; overflow: hidden; font-family: inherit; padding: 0 10px;
  color: #8B949E; font-weight: 500; font-size: 11px;
  transition: all 0.3s ease; white-space: nowrap;
}
.fav-tag-cancel-btn:hover {
  background: #30363D; border-color: #484F58; color: #e8e8e8;
}
.fav-tag-cancel-btn:active { transform: scale(0.97); }
</style>
