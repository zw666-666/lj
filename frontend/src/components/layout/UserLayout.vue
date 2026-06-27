<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue"
import { useRouter, useRoute } from "vue-router"
import { useAuthStore } from "@/stores/auth"
import { useCompareBasketStore } from "@/stores/compareBasket"
import {
  Search, Files, ChatDotSquare, User,
  ArrowDown, Setting, SwitchButton, Star, Edit, Delete, Plus,
  Expand, Fold,
} from "@element-plus/icons-vue"
import VipBadge from "@/components/common/VipBadge.vue"
import api from "@/api/client"
import { ElMessage, ElMessageBox } from "element-plus"

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const basket = useCompareBasketStore()
const collapsed = ref(false)

// 首页（Landing）模式下，侧边栏只显示 Logo
const isLanding = computed(() => route.path === "/landing")

const showProfileDialog = ref(false)
const profileForm = ref({ nickname: "", avatar_url: "" })
function openProfileDialog() {
  profileForm.value = { nickname: auth.user?.nickname || "", avatar_url: auth.user?.avatar_url || "" }
  showProfileDialog.value = true
}
async function saveProfile() {
  const body: any = {}
  if (profileForm.value.nickname && profileForm.value.nickname !== auth.user?.nickname) body.nickname = profileForm.value.nickname
  if (profileForm.value.avatar_url && profileForm.value.avatar_url !== auth.user?.avatar_url) body.avatar_url = profileForm.value.avatar_url
  if (!Object.keys(body).length) { showProfileDialog.value = false; return }
  try { await api.put("/user/profile", body); await auth.fetchProfile(); ElMessage.success("资料已更新"); showProfileDialog.value = false }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "更新失败") }
}
async function handleAvatarUpload(file: any) {
  const reader = new FileReader()
  reader.onload = (e) => { profileForm.value.avatar_url = e.target?.result as string }
  reader.readAsDataURL(file); return false
}

function handleLogout() { basket.clearAll(); auth.logout(); router.push("/login") }
async function deleteAccount() {
  try { await ElMessageBox.confirm("确定注销当前账号？此操作不可恢复。","注销账号",{confirmButtonText:"确认注销",cancelButtonText:"取消",type:"error"}) }
  catch { return }
  try {
    await api.delete("/user/account")
    if (auth.user) {
      // 从所有关联账号的列表中移除当前账号
      const myList = loadUserList(auth.user.id)
      for (const acc of myList) {
        if (acc.id !== auth.user.id) removeFromList(acc.id, auth.user.id)
      }
      localStorage.removeItem(accountKey(auth.user.id))
      localStorage.removeItem(`lvjing_compare_basket_${auth.user.id}`)
      const tokens = loadTokens(); delete tokens[auth.user.id]; saveTokens(tokens)
    }
    basket.clearAll(); auth.logout(); router.push("/login"); ElMessage.success("账号已注销")
  } catch (e:any) { ElMessage.error(e?.response?.data?.detail||"注销失败") }
}

const navItems = [
  { path: "/home", label: "类案检索", icon: Search },
  { path: "/compare", label: "对标分析", icon: Files },
  { path: "/qa", label: "智能问答", icon: ChatDotSquare },
  { path: "/workspace", label: "工作台", icon: User },
]
const activeNav = computed(() => {
  const p = route.path; if (p === "/" || p === "/home") return "/home"
  for (const item of navItems) { if (p.startsWith(item.path)) return item.path }; return ""
})

// --- 账号管理（双向关联 + 按用户隔离 + token 全局单例） ---
interface SavedAccount { id: number; nickname: string; email: string; avatar_url: string }
const TOKENS_KEY = "lvjing_account_tokens"

function accountKey(uid: number | string): string { return `lvjing_accounts_${uid}` }
function loadUserList(uid: number | string): SavedAccount[] { try { return JSON.parse(localStorage.getItem(accountKey(uid)) || "[]") } catch { return [] } }
function saveUserList(uid: number | string, list: SavedAccount[]) { try { localStorage.setItem(accountKey(uid), JSON.stringify(list)) } catch (e) { ElMessage.error("存储空间不足，请清理浏览器缓存") } }

function loadTokens(): Record<number, { token: string; refreshToken: string }> { try { return JSON.parse(localStorage.getItem(TOKENS_KEY) || "{}") } catch { return {} } }
function saveTokens(t: Record<number, { token: string; refreshToken: string }>) { try { localStorage.setItem(TOKENS_KEY, JSON.stringify(t)) } catch { /* quota */ } }

function addToList(uid: number | string, acc: SavedAccount) { const list = loadUserList(uid).filter(a => String(a.id) !== String(acc.id)); list.push(acc); saveUserList(uid, list) }
function removeFromList(uid: number | string, accId: number | string) { saveUserList(uid, loadUserList(uid).filter(a => String(a.id) !== String(accId))) }

const showAccountDialog = ref(false); const accountTab = ref<"accounts"|"add"|"password"|"phone">("accounts")

// 新用户绑定手机号弹窗
const showBindPrompt = ref(false)
const bindPromptForm = ref({ phone: "", code: "" })
const bindPromptSending = ref(false); const bindPromptCd = ref(0)
let bindPromptTimer: number | null = null

onMounted(() => {
  // 刚注册完 → 弹绑定手机号
  if (route.query.new_user === "1" && auth.user && !auth.user.phone) {
    setTimeout(() => { showBindPrompt.value = true }, 800)
  }
})

function sendPromptSms() {
  if (!bindPromptForm.value.phone) { ElMessage.warning("请输入手机号"); return }
  bindPromptSending.value = true
  api.post("/auth/sms/send-code", { scene: "bind", phone: bindPromptForm.value.phone }).then(() => { bindPromptCd.value = 60; bindPromptTimer = window.setInterval(() => { bindPromptCd.value--; if (bindPromptCd.value <= 0 && bindPromptTimer) { clearInterval(bindPromptTimer); bindPromptTimer = null } }, 1000) }).catch((e:any) => ElMessage.error(e?.response?.data?.detail||"发送失败")).finally(() => { bindPromptSending.value = false })
}
async function doBindPrompt() {
  if (!bindPromptForm.value.phone || !bindPromptForm.value.code) { ElMessage.warning("请填写完整"); return }
  try { await api.post("/auth/phone/bind", { phone: bindPromptForm.value.phone, sms_code: bindPromptForm.value.code }); ElMessage.success("手机号绑定成功"); showBindPrompt.value = false; await auth.fetchProfile() }
  catch (e:any) { ElMessage.error(e?.response?.data?.detail||"绑定失败") }
}
const pwdForm = ref({ oldPassword: "", newPassword: "" }); const phoneForm = ref({ phone: "", code: "" })
const savedAccounts = ref<SavedAccount[]>([]); const switchingId = ref<number | null>(null)
const newAccount = ref({ account: "", password: "" }); const addingAccount = ref(false)
const changingPwd = ref(false); const sendingSms = ref(false); const smsCooldown = ref(0)
let smsTimer: number | null = null; const bindingPhone = ref(false)
const unbindingPhone = ref(false)

async function doUnbindPhone() {
  try {
    await ElMessageBox.confirm("确定要解绑手机号吗？解绑后需重新绑定才能使用验证码登录。", "确认解绑", {
      confirmButtonText: "确认解绑",
      cancelButtonText: "取消",
      type: "warning",
    })
  } catch { return }
  unbindingPhone.value = true
  try {
    await api.post("/auth/phone/unbind")
    ElMessage.success("手机号已解绑")
    await auth.fetchProfile()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "解绑失败")
  } finally {
    unbindingPhone.value = false
  }
}

async function doAddAccount() {
  if (!newAccount.value.account || !newAccount.value.password) { ElMessage.warning("请填写完整"); return }
  addingAccount.value = true
  try {
    const rawApi = (await import("axios")).default.create({ baseURL: "/api", timeout: 15000 })
    const loginRes = await rawApi.post("/auth/login", { account: newAccount.value.account, password: newAccount.value.password })
    const { access_token, refresh_token } = loginRes.data
    const profileRes = await rawApi.get("/auth/me", { headers: { Authorization: `Bearer ${access_token}` } })
    const p = profileRes.data
    const newAcc: SavedAccount = { id: p.id, nickname: p.nickname || "", email: p.email || "", avatar_url: p.avatar_url || "" }
    if (auth.user) {
      const curAcc: SavedAccount = { id: auth.user.id, nickname: auth.user.nickname || "", email: auth.user.email || "", avatar_url: auth.user.avatar_url || "" }
      addToList(auth.user.id, newAcc)
      addToList(newAcc.id, curAcc)
      // token 存全局单例
      const tokens = loadTokens()
      tokens[newAcc.id] = { token: access_token, refreshToken: refresh_token }
      tokens[auth.user.id] = { token: auth.token, refreshToken: auth.refreshToken }
      saveTokens(tokens)
    }
    refreshSavedAccounts(); ElMessage.success("账号已保存"); newAccount.value = { account: "", password: "" }; accountTab.value = "accounts"
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (Array.isArray(detail)) { ElMessage.error(detail.map((d:any) => d.msg || JSON.stringify(d)).join("；")) }
    else if (typeof detail === "string") { ElMessage.error(detail) }
    else { ElMessage.error(e?.message || "添加失败") }
  }
  finally { addingAccount.value = false }
}

async function doChangePwd() {
  if (!pwdForm.value.oldPassword || !pwdForm.value.newPassword) { ElMessage.warning("请填写完整"); return }
  changingPwd.value = true
  try { await api.put("/user/password", { old_password: pwdForm.value.oldPassword, new_password: pwdForm.value.newPassword }); ElMessage.success("密码已修改"); pwdForm.value = { oldPassword: "", newPassword: "" } }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "修改失败") }
  finally { changingPwd.value = false }
}

function sendBindSms() {
  if (!phoneForm.value.phone) { ElMessage.warning("请输入手机号"); return }
  sendingSms.value = true
  api.post("/auth/sms/send-code", { scene: "bind", phone: phoneForm.value.phone }).then(() => { ElMessage.success("验证码已发送"); smsCooldown.value = 60; smsTimer = window.setInterval(() => { smsCooldown.value--; if (smsCooldown.value <= 0 && smsTimer) { clearInterval(smsTimer); smsTimer = null } }, 1000) }).catch((e: any) => ElMessage.error(e?.response?.data?.detail || "发送失败")).finally(() => { sendingSms.value = false })
}

async function doBindPhone() {
  if (!phoneForm.value.phone || !phoneForm.value.code) { ElMessage.warning("请填写完整"); return }
  bindingPhone.value = true
  try { await api.post("/auth/phone/bind", { phone: phoneForm.value.phone, sms_code: phoneForm.value.code }); ElMessage.success("手机号绑定成功"); phoneForm.value = { phone: "", code: "" }; accountTab.value = "accounts"; await auth.fetchProfile() }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "绑定失败") }
  finally { bindingPhone.value = false }
}

function refreshSavedAccounts() {
  if (!auth.user) return
  const uid = auth.user.id
  const list = loadUserList(uid).filter(a => String(a.id) !== String(uid))
  list.unshift({ id: uid, nickname: auth.user.nickname || "", email: auth.user.email || "", avatar_url: auth.user.avatar_url || "" })
  savedAccounts.value = list
}

function openAccountDialog() {
  pwdForm.value = { oldPassword: "", newPassword: "" }
  phoneForm.value = { phone: "", code: "" }
  newAccount.value = { account: "", password: "" }
  refreshSavedAccounts(); accountTab.value = "accounts"; showAccountDialog.value = true
  cleanupDeadAccounts()
}

// 自动清理已被管理员注销的账号
async function cleanupDeadAccounts() {
  if (!auth.user) return
  const tokens = loadTokens()
  const list = loadUserList(auth.user.id)
  let changed = false
  for (const acc of list) {
    if (String(acc.id) === String(auth.user.id)) continue
    const stored = tokens[acc.id]
    if (!stored) continue
    // 用保存的 token 试探是否还有效
    try {
      const rawApi = (await import("axios")).default.create({ baseURL: "/api", timeout: 5000 })
      await rawApi.get("/auth/me", { headers: { Authorization: `Bearer ${stored.token}` } })
    } catch {
      // token 失效 → 账号可能已被注销，自动移除
      removeFromList(auth.user.id, acc.id)
      removeFromList(acc.id, auth.user.id)
      delete tokens[acc.id]
      changed = true
    }
  }
  if (changed) {
    saveTokens(tokens)
    refreshSavedAccounts()
  }
}

async function switchToAccount(acc: SavedAccount) {
  const tokens = loadTokens()
  const stored = tokens[acc.id]
  if (!stored) { ElMessage.error("该账号登录已过期，请重新添加"); return }
  switchingId.value = acc.id
  try {
    // 先尝试用 refresh token 换新 token
    try {
      const refreshRes = await api.post("/auth/refresh", { refresh_token: stored.refreshToken })
      stored.token = refreshRes.data.access_token
      stored.refreshToken = refreshRes.data.refresh_token
      tokens[acc.id] = stored
      saveTokens(tokens)
    } catch { /* refresh 失败就用旧 token 试试 */ }
    auth.setTokens(stored.token, stored.refreshToken)
    const ok = await auth.tryFetchProfile()
    if (!ok) {
      // 账号已被注销 → 自动清理
      if (auth.user) {
        removeFromList(auth.user.id, acc.id)
        removeFromList(acc.id, auth.user.id)
      }
      delete tokens[acc.id]; saveTokens(tokens)
      refreshSavedAccounts()
      ElMessage.error("该账号已被注销，已自动移除")
      switchingId.value = null
      return
    }
    refreshSavedAccounts(); router.push("/home"); setTimeout(() => window.location.reload(), 100)
  } finally { switchingId.value = null }
}

function removeSavedAccount(acc: SavedAccount) {
  if (!auth.user) return
  // 双向移除
  removeFromList(auth.user.id, acc.id)
  removeFromList(acc.id, auth.user.id)
  refreshSavedAccounts()
  ElMessage.success("已移除")
}
</script>

<template>
  <div class="app-shell">
    <!-- 侧边栏 -->
    <aside class="sidebar" :class="{ collapsed, 'landing-mode': isLanding }">
      <!-- Logo -->
      <div class="sidebar-logo" @click="router.push('/landing')">
        <span class="logo-icon">&#x2696;</span>
        <span v-if="!collapsed || isLanding" class="logo-text">律 镜</span>
      </div>

      <!-- 导航 -->
      <nav v-if="!isLanding" class="sidebar-nav">
        <div v-for="item in navItems" :key="item.path" class="nav-item"
          :class="{ active: activeNav === item.path }" @click="router.push(item.path)">
          <el-icon><component :is="item.icon" /></el-icon>
          <span v-if="!collapsed" class="nav-label">{{ item.label }}</span>
          <el-badge v-if="item.path === '/compare' && basket.count > 0" :value="basket.count" type="primary" />
        </div>
      </nav>

      <!-- 折叠按钮 -->
      <button v-if="!isLanding" class="sidebar-toggle" @click="collapsed = !collapsed">
        <span class="bar bar1"></span>
        <span class="bar bar2"></span>
        <span class="bar bar1"></span>
      </button>

      <!-- 底部用户 -->
      <div v-if="!isLanding" class="sidebar-user" @click="!collapsed ? undefined : openProfileDialog()">
        <el-dropdown trigger="click" v-if="!collapsed">
          <div class="user-block">
            <el-avatar :size="32" :src="auth.user?.avatar_url || undefined" icon="UserFilled" />
            <div class="user-info">
              <span class="user-name">{{ auth.user?.nickname || "用户" }}</span>
              <VipBadge v-if="auth.isPremium" />
            </div>
            <el-icon><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="openProfileDialog"><el-icon><Edit /></el-icon> 编辑资料</el-dropdown-item>
              <el-dropdown-item @click="router.push('/pricing')"><el-icon><Star /></el-icon> 会员中心</el-dropdown-item>
              <el-dropdown-item v-if="auth.isAdmin" @click="router.push('/admin')"><el-icon><Setting /></el-icon> 管理后台</el-dropdown-item>
              <el-dropdown-item divided @click="openAccountDialog"><el-icon><SwitchButton /></el-icon> 账号管理</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-avatar v-else :size="32" :src="auth.user?.avatar_url || undefined" icon="UserFilled" style="cursor:pointer" />
      </div>
    </aside>

    <!-- 主内容 -->
    <main class="main-content" :class="{ shifted: !collapsed && !isLanding, 'landing-main': isLanding }">
      <RouterView v-slot="{ Component }">
        <KeepAlive :include="['CompareView', 'HomeView']">
          <component :is="Component" />
        </KeepAlive>
      </RouterView>
    </main>
  </div>

  <!-- 编辑个人资料 -->
  <el-dialog v-model="showProfileDialog" title="编辑个人资料" width="400px">
    <el-form label-width="70px">
      <el-form-item label="头像">
        <div style="display:flex;align-items:center;gap:12px">
          <el-avatar :size="48" :src="profileForm.avatar_url || undefined" icon="UserFilled" />
          <el-upload :show-file-list="false" accept="image/*" :before-upload="handleAvatarUpload">
            <el-button size="small">上传照片</el-button>
          </el-upload>
        </div>
      </el-form-item>
      <el-form-item label="用户名"><el-input v-model="profileForm.nickname" maxlength="20" /></el-form-item>
    </el-form>
    <template #footer><el-button @click="showProfileDialog = false">取消</el-button><el-button type="primary" @click="saveProfile">保存</el-button></template>
  </el-dialog>

  <!-- 账号管理 -->
  <el-dialog v-model="showAccountDialog" title="账号管理" width="500px">
    <div style="margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap">
      <button class="acct-tab-btn" :class="{ active: accountTab==='accounts' }" @click="accountTab='accounts'">已保存账号</button>
      <button class="acct-tab-btn" :class="{ active: accountTab==='add' }" @click="accountTab='add'">添加账号</button>
      <button class="acct-tab-btn" :class="{ active: accountTab==='password' }" @click="accountTab='password'">修改密码</button>
      <button class="acct-tab-btn" :class="{ active: accountTab==='phone' }" @click="accountTab='phone'">{{ auth.user?.phone ? '手机号解绑' : '绑定手机号' }}</button>
    </div>

    <template v-if="accountTab==='accounts'">
      <div v-if="savedAccounts.length" style="max-height:300px;overflow-y:auto">
        <div v-for="acc in savedAccounts" :key="acc.id" class="acct-row" :class="{current: auth.user && String(acc.id)===String(auth.user.id)}">
          <el-avatar :size="32" :src="acc.avatar_url||undefined" icon="UserFilled" />
          <div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600">{{ acc.nickname||acc.email }}</div><div style="font-size:11px;color:#8B949E">{{ acc.email }}</div></div>
          <template v-if="auth.user&&String(acc.id)===String(auth.user.id)">
            <el-tag size="small" type="success">当前</el-tag>
          </template>
          <template v-else>
            <el-button size="small" :loading="switchingId===acc.id" @click="switchToAccount(acc)">切换</el-button>
            <button class="del-btn" @click="removeSavedAccount(acc)">
              <svg class="trash-svg" viewBox="0 -10 64 74" xmlns="http://www.w3.org/2000/svg">
                <g><rect x="16" y="24" width="32" height="30" rx="3" ry="3" fill="#e74c3c"/><g transform-origin="12 18" id="lid-group"><rect x="12" y="12" width="40" height="6" rx="2" ry="2" fill="#c0392b"/><rect x="26" y="8" width="12" height="4" rx="2" ry="2" fill="#c0392b"/></g></g>
              </svg>
            </button>
          </template>
        </div>
      </div>
      <el-empty v-else description="暂无已保存账号" :image-size="40" />
    </template>

    <template v-else-if="accountTab==='add'">
      <el-form label-width="80px"><el-form-item label="邮箱/手机"><el-input v-model="newAccount.account" /></el-form-item><el-form-item label="密码"><el-input v-model="newAccount.password" type="password" show-password /></el-form-item><el-form-item>
        <button class="save-acct-btn" @click="doAddAccount" :disabled="addingAccount">
          <span class="save-acct-text">{{ addingAccount ? '保存中...' : '保存账号' }}</span>
          <span class="save-acct-icon">
            <svg fill="none" height="24" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" viewBox="0 0 24 24" width="24" xmlns="http://www.w3.org/2000/svg">
              <line x1="12" x2="12" y1="5" y2="19"></line>
              <line x1="5" x2="19" y1="12" y2="12"></line>
            </svg>
          </span>
        </button>
      </el-form-item></el-form>
    </template>

    <template v-else-if="accountTab==='password'">
      <el-form label-width="80px"><el-form-item label="原密码"><el-input v-model="pwdForm.oldPassword" type="password" show-password /></el-form-item><el-form-item label="新密码"><el-input v-model="pwdForm.newPassword" type="password" show-password placeholder="8-64位，需含字母和数字" /></el-form-item><el-form-item><el-button type="primary" :loading="changingPwd" @click="doChangePwd" style="width:100%">修改密码</el-button></el-form-item></el-form>
    </template>

    <template v-else-if="accountTab==='phone'">
      <!-- 已绑定：显示解绑 -->
      <template v-if="auth.user?.phone">
        <div style="text-align:center;padding:16px 0">
          <p style="color:#8B949E;font-size:13px;margin-bottom:16px">当前绑定的手机号</p>
          <p style="color:#F0F6FC;font-size:22px;font-weight:700;letter-spacing:0.1em;margin-bottom:8px">
            {{ auth.user.phone.slice(0, 3) + '****' + auth.user.phone.slice(-4) }}
          </p>
          <p style="color:#484F58;font-size:12px;margin-bottom:24px">为保护隐私，中间四位已隐藏</p>
          <el-button type="danger" plain @click="doUnbindPhone" :loading="unbindingPhone">立即解绑</el-button>
        </div>
      </template>
      <!-- 未绑定：显示绑定 -->
      <template v-else>
        <el-form label-width="80px"><el-form-item label="手机号"><el-input v-model="phoneForm.phone" placeholder="输入要绑定的手机号" /></el-form-item><el-form-item label="验证码"><div style="display:flex;gap:8px"><el-input v-model="phoneForm.code" placeholder="短信验证码" /><el-button type="primary" :loading="sendingSms" :disabled="smsCooldown > 0" @click="sendBindSms">{{ smsCooldown > 0 ? smsCooldown + 's' : '获取验证码' }}</el-button></div></el-form-item><el-form-item><el-button type="primary" :loading="bindingPhone" @click="doBindPhone" style="width:100%">绑定手机号</el-button></el-form-item></el-form>
      </template>
    </template>
    <template #footer>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <button class="delete-acct-btn" @click="deleteAccount">
          <span>注销</span>
          <span class="delete-icon">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke-miterlimit="2" stroke-linejoin="round" fill-rule="evenodd" clip-rule="evenodd"><path fill-rule="nonzero" d="m12.002 2.005c5.518 0 9.998 4.48 9.998 9.997 0 5.518-4.48 9.998-9.998 9.998-5.517 0-9.997-4.48-9.997-9.998 0-5.517 4.48-9.997 9.997-9.997zm0 1.5c-4.69 0-8.497 3.807-8.497 8.497s3.807 8.498 8.497 8.498 8.498-3.808 8.498-8.498-3.808-8.497-8.498-8.497zm0 7.425 2.717-2.718c.146-.146.339-.219.531-.219.404 0 .75.325.75.75 0 .193-.073.384-.219.531l-2.717 2.717 2.727 2.728c.147.147.22.339.22.531 0 .427-.349.75-.75.75-.192 0-.384-.073-.53-.219l-2.729-2.728-2.728 2.728c-.146.146-.338.219-.53.219-.401 0-.751-.323-.751-.75 0-.192.073-.384.22-.531l2.728-2.728-2.722-2.722c-.146-.147-.219-.338-.219-.531 0-.425.346-.749.75-.749.192 0 .385.073.531.219z"></path></svg>
          </span>
        </button>
        <button class="logout-btn" @click="handleLogout">
          <div class="logout-sign">
            <svg viewBox="0 0 512 512"><path d="M377.9 105.9L500.7 228.7c7.2 7.2 11.3 17.1 11.3 27.3s-4.1 20.1-11.3 27.3L377.9 406.1c-6.4 6.4-15 9.9-24 9.9c-18.7 0-33.9-15.2-33.9-33.9l0-62.1-128 0c-17.7 0-32-14.3-32-32l0-64c0-17.7 14.3-32 32-32l128 0 0-62.1c0-18.7 15.2-33.9 33.9-33.9c9 0 17.6 3.6 24 9.9zM160 96L96 96c-17.7 0-32 14.3-32 32l0 256c0 17.7 14.3 32 32 32l64 0c17.7 0 32 14.3 32 32s-14.3 32-32 32l-64 0c-53 0-96-43-96-96L0 128C0 75 43 32 96 32l64 0c17.7 0 32 14.3 32 32s-14.3 32-32 32z"></path></svg>
          </div>
          <div class="logout-text">退出</div>
        </button>
      </div>
    </template>
  </el-dialog>

  <!-- 新用户绑定手机号弹窗 -->
  <el-dialog v-model="showBindPrompt" title="绑定手机号" width="400px" :close-on-click-modal="false" :close-on-press-escape="false">
    <p style="color:#8B949E;font-size:13px;margin-bottom:16px">绑定手机号后可使用验证码登录，方便快捷</p>
    <el-form label-width="80px">
      <el-form-item label="手机号"><el-input v-model="bindPromptForm.phone" placeholder="输入手机号" /></el-form-item>
      <el-form-item label="验证码">
        <div style="display:flex;gap:8px"><el-input v-model="bindPromptForm.code" placeholder="短信验证码" /><el-button type="primary" :loading="bindPromptSending" :disabled="bindPromptCd > 0" @click="sendPromptSms">{{ bindPromptCd > 0 ? bindPromptCd + 's' : '获取验证码' }}</el-button></div>
      </el-form-item>
      <el-form-item><el-button type="primary" @click="doBindPrompt" style="width:100%">绑定手机号</el-button></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showBindPrompt = false">暂不绑定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.app-shell { display: flex; min-height: 100vh; background: #0F0F0F; }

/* ====== 侧边栏 ====== */
.sidebar {
  width: 215px; flex-shrink: 0; background: transparent;
  border-right: 1px solid #30363D; display: flex; flex-direction: column;
  transition: width 0.25s cubic-bezier(0.22,1,0.36,1);
  position: fixed; top: 0; left: 0; height: 100vh; z-index: 50;
}
.sidebar.collapsed { width: 50px; }
.sidebar.collapsed .nav-label,
.sidebar.collapsed .logo-text,
.sidebar.collapsed .user-info,
.sidebar.collapsed .user-block .el-icon,
.sidebar.collapsed .vip-badge { display: none; }
.sidebar.collapsed .sidebar-logo { justify-content: center; padding: 20px 0; }
.sidebar.collapsed .nav-item { justify-content: center; padding: 10px 0; }
.sidebar.collapsed .sidebar-user { display: flex; justify-content: center; }

/* 首页（Landing）模式：侧边栏只显示 Logo */
.sidebar.landing-mode { width: 130px; border-right: none; }
.sidebar.landing-mode .sidebar-logo { justify-content: center; padding: 20px 0; border-bottom: none; }

.sidebar-logo {
  display: flex; align-items: center; gap: 10px; padding: 20px 18px;
  cursor: pointer; border-bottom: 1px solid #21262D;
}
.logo-icon { font-size: 26px; color: #58A6FF; }
.logo-text { font-size: 18px; font-weight: 700; color: #F0F6FC; letter-spacing: 0.15em; font-family: "PingFang SC","Noto Serif SC","SimSun",serif; }

.sidebar-nav { flex: 1; padding: 12px 8px; display: flex; flex-direction: column; gap: 2px; overflow-y: auto; }
.nav-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 14px;
  cursor: pointer; color: #8B949E; font-size: 14px;
  transition: all 0.3s; white-space: nowrap; position: relative;
  overflow: hidden; border: 1px solid transparent; border-radius: 8px;
}
.nav-item::before {
  content: ""; position: absolute; z-index: -1;
  width: 400px; height: 400px; border-radius: 50%;
  background: #2F65FF; top: 100%; left: 0;
  transition: 500ms ease;
}
.nav-item:hover { color: #fff; letter-spacing: 1px; border-color: #58A6FF; }
.nav-item:hover::before { top: 50%; left: 50%; transform: translate(-50%,-50%); background: #58A6FF; }
.nav-item.active { color: #fff; border-color: #2F65FF; font-weight: 600; }
.nav-item.active::before { top: 50%; left: 50%; transform: translate(-50%,-50%); background: #2F65FF; }

.sidebar-toggle {
  width: 28px; height: 28px; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 3px;
  background: transparent; border-radius: 6px; cursor: pointer;
  border: none; margin: 0 0 0 14px; outline: none; padding: 0;
}
.bar {
  width: 16px; height: 1.5px; background: #8B949E;
  display: flex; align-items: center; justify-content: center;
  position: relative; border-radius: 1px; transition: background 0.2s;
}
.bar::before {
  content: ""; width: 3px; height: 3px; background: #58A6FF;
  position: absolute; border-radius: 50%;
  box-shadow: 0 0 3px rgba(88,166,255,0.5); transition: transform 0.3s;
}
.bar1::before { transform: translateX(-5px); }
.bar2::before { transform: translateX(5px); }
.sidebar-toggle:hover .bar { background: #F0F6FC; }
.sidebar-toggle:hover .bar1::before { transform: translateX(5px); }
.sidebar-toggle:hover .bar2::before { transform: translateX(-5px); }

.sidebar-user { padding: 12px; border-top: 1px solid #21262D; }
.sidebar.collapsed .sidebar-user { padding: 9px 5px; display: flex; justify-content: center; }
.user-block { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.user-info { flex: 1; min-width: 0; display: flex; align-items: center; gap: 4px; }
.user-name { font-size: 13px; color: #F0F6FC; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ====== 主内容 ====== */
.main-content { flex: 1; min-width: 0; padding: 24px 24px 24px 88px; overflow-y: auto; min-height: 100vh; transition: padding-left 0.25s cubic-bezier(0.22,1,0.36,1); }
.main-content.shifted { padding-left: 263px; }
.main-content.landing-main { padding-left: 154px; padding-right: 154px; }

.acct-row { display: flex; align-items: center; gap: 10px; padding: 10px; border-radius: 8px; margin-bottom: 4px; background: #0D1117; border:1px solid #21262D; }
.acct-row.current { border-color: #30363D; }

.del-btn {
  padding: 0; border: none; background: transparent; cursor: pointer;
  transition: transform 0.2s ease; flex-shrink: 0;
}
.del-btn:hover { transform: scale(1.1); }
.del-btn:active { transform: scale(0.95); }
.trash-svg {
  width: 28px; height: 28px; transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1);
  overflow: visible;
}
.del-btn:hover .trash-svg { transform: rotate(3deg); }
.del-btn:hover #lid-group { transform: rotate(-28deg) translateY(2px); transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1); }
.del-btn:active #lid-group { transform: rotate(-12deg) scale(0.98); }
:deep(.el-dialog .el-button) { border-radius: 8px !important; }

/* 账号管理标签按钮 */
.acct-tab-btn {
  padding: 0.35em 0.9em; font-size: 12px; letter-spacing: 0.5px;
  font-weight: 500; color: #8B949E; background: #1F1F1F;
  border: 1px solid #30363D; border-radius: 8px; cursor: pointer;
  box-shadow: 0px 4px 10px rgba(0,0,0,0.15); transition: all 0.3s ease;
  outline: none; font-family: inherit;
}
.acct-tab-btn:hover {
  background: #58A6FF; border-color: #58A6FF; color: #fff;
  box-shadow: 0px 12px 20px rgba(88,166,255,0.35); transform: translateY(-5px);
}
.acct-tab-btn.active {
  background: #2F65FF; border-color: #2F65FF; color: #fff;
  box-shadow: 0px 8px 15px rgba(47,101,255,0.3);
}
.acct-tab-btn:active { transform: translateY(-1px); }

/* 保存账号按钮 */
.save-acct-btn {
  position: relative; width: 100%; height: 32px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid #2F65FF; background: #2F65FF;
  border-radius: 8px; overflow: hidden; font-family: inherit; padding: 0;
}
.save-acct-btn:hover { background: #2F65FF; border-color: #2F65FF; }
.save-acct-btn:active { background: #1D4ED8; border-color: #1D4ED8; }
.save-acct-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.save-acct-text {
  color: #fff; font-weight: 600; font-size: 12px;
  transition: transform 0.3s;
}
.save-acct-btn:not(:disabled):hover .save-acct-text { transform: translateX(80px); }
.save-acct-icon {
  position: absolute; right: 0; height: 100%; width: 32px;
  background: #2F65FF; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.3s; opacity: 0;
}
.save-acct-btn:not(:disabled):hover .save-acct-icon { width: 100%; left: 0; opacity: 1; }
.save-acct-icon svg { width: 16px; color: #fff; }

/* 注销按钮 */
.delete-acct-btn {
  position: relative; display: flex; align-items: center; justify-content: center;
  gap: 5px; padding: 0.35em 0.9em; background: #0D1117; border: none;
  font: inherit; color: #e8e8e8; font-size: 12px; font-weight: 500;
  border-radius: 8px; cursor: pointer; overflow: hidden;
  transition: all 0.3s cubic-bezier(0.23,1,0.32,1); letter-spacing: 0.5px;
}
.delete-acct-btn span { position: relative; z-index: 2; display: flex; align-items: center; }
.delete-acct-btn::before {
  position: absolute; content: ''; width: 100%; height: 100%;
  translate: 0 105%; background: #F53844;
  transition: all 0.3s cubic-bezier(0.23,1,0.32,1);
}
.delete-icon svg { width: 18px; height: 18px; fill: #F53844; transition: all 0.3s cubic-bezier(0.23,1,0.32,1); }
.delete-acct-btn:hover { animation: shake 0.2s linear 1; }
.delete-acct-btn:hover::before { translate: 0 0; }
.delete-acct-btn:hover .delete-icon svg { fill: #e8e8e8; }
@keyframes shake {
  0% { rotate: 0deg; }
  33% { rotate: 10deg; }
  66% { rotate: -10deg; }
  100% { rotate: 10deg; }
}

/* 退出登录按钮 */
.logout-btn {
  display: flex; align-items: center; justify-content: flex-start;
  width: 28px; height: 28px; border: none; border-radius: 5px;
  cursor: pointer; position: relative; overflow: hidden;
  transition-duration: .3s; padding: 0;
  box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.2);
  background-color: #2e2e2e;
}
.logout-sign {
  width: 100%; transition-duration: .3s;
  display: flex; align-items: center; justify-content: center;
}
.logout-sign svg { width: 12px; }
.logout-sign svg path { fill: #f3f3f3; }
.logout-text {
  position: absolute; right: 0; width: 0; opacity: 0;
  color: #f3f3f3; font-size: 0.9em; font-weight: 600;
  transition-duration: .3s; white-space: nowrap;
}
.logout-btn:hover {
  width: 88px; border-radius: 5px;
}
.logout-btn:hover .logout-sign { width: 30%; padding-left: 10px; }
.logout-btn:hover .logout-text { opacity: 1; width: 70%; padding-right: 6px; }
.logout-btn:active { transform: translate(2px, 2px); }
:deep(.el-dialog .el-button:not(.el-button--primary):not(.el-button--danger)) { background: #383A43 !important; border-color: #383A43 !important; color: #8B949E !important; }
:deep(.el-dialog .el-button:not(.el-button--primary):not(.el-button--danger):hover) { background: #3F4149 !important; border-color: #555 !important; color: #F0F6FC !important; }

</style>

<style>
.el-dialog .el-button { border-radius: 8px !important; }
.el-dialog .el-button:not(.el-button--primary):not(.el-button--danger) { background: #383A43 !important; border-color: #383A43 !important; color: #8B949E !important; }
.el-dialog .el-button:not(.el-button--primary):not(.el-button--danger):hover { background: #3F4149 !important; border-color: #555 !important; color: #F0F6FC !important; }
</style>
