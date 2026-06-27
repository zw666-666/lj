<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import api from "@/api/client"
import { useAuthStore } from "@/stores/auth"
import { ChatDotSquare, Plus, Delete, View, Close } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Upload } from "@element-plus/icons-vue"
import UpgradePrompt from "@/components/common/UpgradePrompt.vue"

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

interface Message { role: string; content: string; citations?: any[] }
const messages = ref<Message[]>([])
const inputText = ref("")
const loading = ref(false)
const sessions = ref<any[]>([])
const activeSessionId = ref<number | null>(null)
const showHistory = ref(true)

// 配额
const qaRemaining = ref<number>(-1)
const qaUnlimited = ref(true)
const showUpgrade = ref(false)

// 文件上传
const uploadedFileName = ref("")
const uploadedFileContent = ref("")
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadingFile = ref(false)

function handleFileUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  // 限制文件大小 5MB
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.warning("文件过大，请上传 5MB 以内的文本文件")
    input.value = ""
    return
  }
  uploadingFile.value = true
  const reader = new FileReader()
  reader.onload = (ev) => {
    const text = (ev.target?.result as string) || ""
    if (!text.trim()) {
      ElMessage.warning("文件内容为空")
      uploadingFile.value = false
      input.value = ""
      return
    }
    uploadedFileName.value = file.name
    uploadedFileContent.value = text
    uploadingFile.value = false
    ElMessage.success("文件已加载")
  }
  reader.onerror = () => {
    ElMessage.error("文件读取失败")
    uploadingFile.value = false
  }
  reader.readAsText(file, "utf-8")
}

function clearUploadedFile() {
  uploadedFileName.value = ""
  uploadedFileContent.value = ""
  if (fileInputRef.value) fileInputRef.value.value = ""
}

onMounted(async () => {
  await loadSessions()
  await loadQuota()
  const sid = route.params.sessionId
  if (sid) {
    activeSessionId.value = Number(sid)
    await loadMessages(Number(sid))
  }
})

// 监听路由变化，同步 activeSessionId（从侧边栏点击其他会话时）
watch(() => route.params.sessionId, async (newSid) => {
  if (newSid) {
    const nid = Number(newSid)
    if (activeSessionId.value !== nid) {
      activeSessionId.value = nid
      await loadMessages(nid)
    }
  } else {
    // 回到 /qa 无参路由，若当前会话已被删除则清空
    if (!sessions.value.some(s => s.id === activeSessionId.value)) {
      activeSessionId.value = null
      messages.value = []
    }
  }
})

async function loadQuota() {
  try {
    const res = await api.get("/qa/quota")
    qaRemaining.value = res.data.remaining
    qaUnlimited.value = res.data.unlimited
  } catch {}
}

async function loadSessions() {
  if (!auth.isLoggedIn) return
  try {
    const res = await api.get("/qa/sessions")
    sessions.value = res.data
  } catch {}
}

async function loadMessages(sid: number) {
  try {
    const res = await api.get(`/qa/sessions/${sid}/messages`)
    messages.value = res.data.map((m: any) => ({
      role: m.role,
      content: m.content,
      citations: m.citations,
    }))
  } catch {}
}

async function sendMessage() {
  const q = inputText.value.trim()
  if (!q || loading.value) return
  // 携带文件内容
  const fileContent = uploadedFileContent.value
  const fileName = uploadedFileName.value
  inputText.value = ""
  const displayContent = fileContent
    ? `${q}\n\n[已上传文件：${fileName}]`
    : q
  messages.value.push({ role: "user", content: displayContent })
  // 发送后清除文件
  if (fileContent) clearUploadedFile()
  loading.value = true

  try {
    const token = auth.token
    const res = await fetch("/api/qa/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        question: q,
        session_id: activeSessionId.value,
        file_content: fileContent || undefined,
        file_name: fileName || undefined,
      }),
    })

    if (res.status === 429) {
      // 次数用完
      await loadQuota()
      showUpgrade.value = true
      messages.value.pop()  // 移除刚添加的用户消息
      loading.value = false
      return
    }
    if (!res.ok || !res.body) throw new Error("Request failed")

    // 从响应头读取新建的会话 ID（比 SSE 更可靠）
    const newSessionId = res.headers.get("X-Session-Id")
    if (newSessionId && !activeSessionId.value) {
      activeSessionId.value = Number(newSessionId)
      await loadSessions()
      router.replace(`/qa/${newSessionId}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    const aiMsg: Message = { role: "assistant", content: "", citations: [] }
    let sseBuffer = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      sseBuffer += decoder.decode(value, { stream: true })
      // SSE 事件以 \n\n 分隔，按完整事件解析
      const events = sseBuffer.split("\n\n")
      sseBuffer = events.pop() || ""
      for (const evt of events) {
        const line = evt.trim()
        if (!line.startsWith("data: ")) continue
        try {
          const data = JSON.parse(line.slice(6))
          if (data.done) { sseBuffer = ""; break }
          if (data.session_id && !activeSessionId.value) {
            activeSessionId.value = data.session_id
            await loadSessions()
            router.replace(`/qa/${data.session_id}`)
          }
          if (data.content) aiMsg.content += data.content
          if (data.citations) aiMsg.citations = data.citations
        } catch {
          aiMsg.content += line.slice(6)
        }
      }
    }
    messages.value.push(aiMsg)
    if (!activeSessionId.value) await loadSessions()
    await loadQuota()  // 刷新配额
  } catch {
    messages.value.push({ role: "assistant", content: "抱歉，服务暂时不可用，请稍后重试。" })
  } finally {
    loading.value = false
    await nextTick()
    const container = document.getElementById("qa-messages")
    if (container) container.scrollTop = container.scrollHeight
  }
}

async function newSession() {
  messages.value = []
  activeSessionId.value = null
  router.push("/qa")
}

async function openSession(sid: number) {
  activeSessionId.value = sid
  router.push(`/qa/${sid}`)
  await loadMessages(sid)
}

function clearInput() {
  inputText.value = ""
}

async function deleteSession(sid: number, event: Event) {
  event.stopPropagation()
  try {
    await ElMessageBox.confirm("确定删除该对话记录？删除后不可恢复。", "删除确认", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    })
  } catch {
    return
  }
  try {
    await api.delete(`/qa/sessions/${sid}`)
    sessions.value = sessions.value.filter(s => s.id !== sid)
    // 如果删除的是当前正在查看的会话，清空聊天界面
    if (activeSessionId.value === sid || Number(route.params.sessionId) === sid) {
      activeSessionId.value = null
      messages.value = []
      router.push("/qa")
    }
    ElMessage.success("已删除")
  } catch {
    ElMessage.error("删除失败")
  }
}
</script>

<template>
  <div class="qa-layout">
    <!-- 侧边栏：会话历史 -->
    <div class="qa-sidebar" :class="{ hidden: !showHistory }">
      <div class="sidebar-header">
        <h4>问答历史</h4>
        <el-button :icon="Plus" size="small" text @click="newSession">新对话</el-button>
      </div>
      <div class="session-list">
        <div
          v-for="s in sessions" :key="s.id"
          class="session-item"
          :class="{ active: s.id === activeSessionId }"
          @click="openSession(s.id)"
        >
          <el-icon><ChatDotSquare /></el-icon>
          <span class="session-title">{{ s.title || '新对话' }}</span>
          <span class="session-date">{{ s.created_at?.slice(0, 10) }}</span>
          <el-button
            class="session-delete-btn"
            :icon="Close"
            size="small"
            text
            @click="(e: Event) => deleteSession(s.id, e)"
            title="删除此对话"
          />
        </div>
        <el-empty v-if="!sessions.length" description="暂无历史" :image-size="40" />
      </div>
    </div>

    <!-- 主聊天区 -->
    <div class="qa-main">
      <div class="qa-topbar">
        <el-button :icon="View" size="small" text @click="showHistory = !showHistory">
          {{ showHistory ? '隐藏历史' : '显示历史' }}
        </el-button>
        <div style="display:flex;align-items:center;gap:12px;">
          <span v-if="qaUnlimited" class="qa-quota unlimited">会员不限次</span>
          <span v-else class="qa-quota" :class="{ low: qaRemaining <= 2 }">
            今日剩余 <b>{{ qaRemaining }}</b> 次
          </span>
        </div>
      </div>

      <div id="qa-messages" class="qa-messages">
        <div v-if="!messages.length && !loading" class="qa-welcome">
          <div class="welcome-icon">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <rect x="4" y="6" width="34" height="28" rx="4" stroke="#484F58" stroke-width="2" fill="none"/>
              <circle cx="14" cy="20" r="2" fill="#484F58"/>
              <circle cx="21" cy="20" r="2" fill="#484F58"/>
              <circle cx="28" cy="20" r="2" fill="#484F58"/>
              <path d="M38 26l-6 6h12l-6-6z" fill="#484F58"/>
              <rect x="8" y="28" width="16" height="4" rx="2" fill="#484F58" opacity="0.4"/>
              <rect x="8" y="34" width="10" height="4" rx="2" fill="#484F58" opacity="0.25"/>
            </svg>
          </div>
          <h3>法律智能问答</h3>
          <p>基于案例库的限定域 RAG 问答，每个观点附带案例引用</p>
        </div>

        <div
          v-for="(msg, i) in messages" :key="i"
          class="msg-row"
          :class="msg.role"
        >
          <div class="msg-bubble">
            <div class="msg-text">{{ msg.content }}</div>
            <div v-if="msg.citations?.length" class="msg-citations">
              <div v-for="(c, ci) in msg.citations" :key="ci" class="citation-card">
                📎 {{ c.title || c.case_no || '来源' }}
              </div>
            </div>
          </div>
        </div>

        <div v-if="loading" class="msg-row assistant">
          <div class="msg-bubble thinking">
            <span class="dot-pulse">AI 正在检索案例库分析中</span>
          </div>
        </div>
      </div>

      <div class="qa-input-bar">
        <!-- 已上传文件标签 -->
        <div v-if="uploadedFileName" class="qa-file-tag">
          <el-icon><Upload /></el-icon>
          <span class="file-name">{{ uploadedFileName }}</span>
          <el-button :icon="Close" size="small" text circle @click="clearUploadedFile" class="file-clear-btn" />
        </div>
        <div class="qa-search-box">
          <!-- 文件上传按钮 -->
          <button class="qa-upload-btn" @click="fileInputRef?.click()" :disabled="loading || uploadingFile" title="上传文件">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M21.5 11.5L12 21m0 0l-9.5-9.5M12 21V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <input
            ref="fileInputRef"
            type="file"
            accept=".txt,.md,.doc,.docx,.pdf,.json"
            style="display:none"
            @change="handleFileUpload"
          />
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="1"
            :placeholder="uploadedFileName ? '文件已上传，输入问题后发送...' : '输入你的法律问题，AI 将从案例库中检索相关裁判规则并生成回答...'"
            @keyup.enter.exact="sendMessage"
            resize="none"
            :disabled="loading"
            class="qa-search-input"
          />
          <button class="qa-search-btn" @click="sendMessage" :disabled="loading || !inputText.trim()">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 29 29" fill="none">
              <path d="M23.7953 23.9182L19.0585 19.1814M19.0585 19.1814C19.8188 18.4211 20.4219 17.5185 20.8333 16.5251C21.2448 15.5318 21.4566 14.4671 21.4566 13.3919C21.4566 12.3167 21.2448 11.252 20.8333 10.2587C20.4219 9.2653 19.8188 8.36271 19.0585 7.60242C18.2982 6.84214 17.3956 6.23905 16.4022 5.82759C15.4089 5.41612 14.3442 5.20435 13.269 5.20435C12.1938 5.20435 11.1291 5.41612 10.1358 5.82759C9.1424 6.23905 8.23981 6.84214 7.47953 7.60242C5.94407 9.13789 5.08145 11.2204 5.08145 13.3919C5.08145 15.5634 5.94407 17.6459 7.47953 19.1814C9.01499 20.7168 11.0975 21.5794 13.269 21.5794C15.4405 21.5794 17.523 20.7168 19.0585 19.1814Z" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 升级引导 -->
    <UpgradePrompt
      v-model:visible="showUpgrade"
      feature-name="AI智能问答"
      description="今日免费问答次数已用完（每日5次），升级会员即可无限使用AI智能问答。"
    />
  </div>
</template>

<style scoped>
.qa-layout { display: flex; gap: 16px; max-width: 1200px; margin: 0 auto; height: calc(100vh - 100px); animation: fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) both; }
.qa-sidebar {
  width: 240px; flex-shrink: 0; background: #1E1F20;
  border-radius: var(--radius-lg); border: none;
  box-shadow: 0 0 0 1px var(--ring-color);
  display: flex; flex-direction: column; overflow: hidden;
}
.qa-sidebar.hidden { display: none; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid var(--ring-color); }
.sidebar-header h4 { font-size: 15px; color: var(--text-primary); font-weight: 600; }
.session-list { flex: 1; overflow-y: auto; padding: 8px; }
.session-item {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 10px;
  cursor: pointer; font-size: 13px; color: var(--text-secondary);
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1); position: relative;
}
.session-item:hover { background: var(--bg-hover); }
.session-item.active { background: var(--bg-active); color: var(--accent-blue); font-weight: 600; }
.session-delete-btn { opacity: 0; transition: opacity 0.15s; margin-left: auto; flex-shrink: 0; }
.session-item:hover .session-delete-btn { opacity: 1; }
.session-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-date { font-size: 11px; color: var(--text-muted); }

.qa-main {
  flex: 1; display: flex; flex-direction: column; background: #1E1F20;
  border-radius: var(--radius-lg); border: none;
  box-shadow: 0 0 0 1px var(--ring-color); overflow: hidden;
}
.qa-topbar { display: flex; justify-content: space-between; padding: 12px 18px; border-bottom: 1px solid var(--ring-color); }
.qa-messages { flex: 1; overflow-y: auto; padding: 24px; }
.qa-welcome {
  text-align: center; padding: 80px 20px 60px;
  display: flex; flex-direction: column; align-items: center;
}
.welcome-icon { margin-bottom: 20px; opacity: 0.5; }
.qa-welcome h3 {
  font-size: 24px; color: var(--text-primary); margin: 0 0 12px; font-weight: 600;
  letter-spacing: 0.06em;
}
.qa-welcome p { font-size: 13px; color: #484F58; line-height: 1.8; margin: 0; }

.msg-row { margin-bottom: 20px; display: flex; }
.msg-row.user { justify-content: flex-end; }
.msg-row.assistant { justify-content: flex-start; }
.msg-bubble {
  max-width: 80%; padding: 12px 18px; border-radius: 16px; font-size: 14px; line-height: 1.7;
}
.msg-row.user .msg-bubble { background: #2F65FF; color: #fff; border-bottom-right-radius: 6px; }
.msg-row.assistant .msg-bubble {
  background: var(--bg-tertiary); color: var(--text-primary);
  border-bottom-left-radius: 6px;
  box-shadow: 0 0 0 1px var(--ring-color);
}
.msg-bubble.thinking { color: var(--text-tertiary); font-style: italic; }
.dot-pulse::after { content: '...'; animation: dots 1.5s infinite; }
@keyframes dots { 0%,20% { content: '.'; } 40% { content: '..'; } 60%,100% { content: '...'; } }

.msg-citations { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--ring-color); }
.citation-card { font-size: 12px; padding: 6px 10px; background: var(--bg-input); border-radius: 8px; margin-bottom: 4px; color: var(--text-secondary); }

.qa-input-bar { padding: 14px 18px; border-top: 1px solid var(--ring-color); }

.qa-file-tag {
  display: inline-flex; align-items: center; gap: 6px;
  background: rgba(47,101,255,0.12); color: var(--accent-blue);
  border: 1px solid rgba(47,101,255,0.3); border-radius: 20px;
  padding: 4px 12px; margin-bottom: 8px; font-size: 12px; max-width: 100%;
}
.qa-file-tag .file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 300px; font-weight: 500; }
.qa-file-tag .file-clear-btn { color: var(--accent-blue); margin-left: 2px; }

.qa-search-box {
  display: flex; align-items: center; background: #2f3640;
  border-radius: 50px; position: relative; padding: 0 52px 0 0;
  min-height: 50px;
}
.qa-upload-btn {
  width: 44px; height: 50px; flex-shrink: 0; border: 0; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  background: transparent; color: #8B949E; border-radius: 50px 0 0 50px;
  transition: color 0.2s;
}
.qa-upload-btn:hover:not(:disabled) { color: var(--accent-blue); }
.qa-upload-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.qa-search-input { flex: 1; }
.qa-search-input :deep(.el-textarea__inner) {
  background: transparent !important; border: none !important;
  border-radius: 50px !important; color: #F0F6FC !important;
  font-size: 14px; resize: none; box-shadow: none !important;
  padding: 12px 38px 12px 20px !important; line-height: 1.4;
}
.qa-search-input :deep(.el-textarea__inner)::placeholder { color: #8B949E; }
.qa-search-btn {
  position: absolute; right: 6px; width: 40px; height: 40px;
  border-radius: 50%; border: 0; cursor: pointer; display: flex;
  align-items: center; justify-content: center;
  background: linear-gradient(90deg, #2F65FF 0%, #58A6FF 100%);
  transition: all 300ms cubic-bezier(.23,1,0.32,1);
}
.qa-search-btn svg { width: 16px; height: 16px; }
.qa-search-btn:hover {
  transform: translateY(-3px);
  box-shadow: rgba(47,101,255,0.5) 0 10px 20px;
}
.qa-search-btn:active { transform: translateY(0); box-shadow: none; }
.qa-search-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
.qa-quota {
  font-size: 12px; padding: 3px 12px; border-radius: 10px;
  background: var(--bg-active); color: var(--accent-blue); white-space: nowrap; font-weight: 500;
}
.qa-quota.low { background: rgba(197, 48, 48, 0.08); color: var(--accent-red); }
.qa-quota.unlimited { background: rgba(139, 105, 20, 0.08); color: var(--accent-gold-dark); }
.qa-quota b { font-weight: 700; }
</style>
