<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter, useRoute } from "vue-router"
import { useAuthStore } from "@/stores/auth"
import { User, Lock, Message, Loading } from "@element-plus/icons-vue"
import type { FormInstance, FormRules } from "element-plus"
import Plasma from "@/components/common/Plasma.vue"
import { ElMessage } from "element-plus"
import { toDataURL } from "qrcode"

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

type LoginMode = "password" | "sms"
const mode = ref<LoginMode>("password")
const isLogin = ref(true)
const loading = ref(false)
const smsLoading = ref(false)
const errorMsg = ref("")
const formRef = ref<FormInstance>()
const pageLoaded = ref(false)

const form = reactive({
  account: "", password: "", smsCode: "", confirmPassword: "", nickname: "",
})
const cooldown = ref(0)
const cooldownTimer = ref<number | null>(null)
const isPhoneAccount = computed(() => /^1[3-9]\d{9}$/.test(form.account.trim()))

// 短信注册后设置密码 & 用户名
const showSetup = ref(false)
const setupForm = reactive({ password: "", confirmPassword: "", nickname: "" })
const setupLoading = ref(false)
const setupError = ref("")

onMounted(() => {
  requestAnimationFrame(() => { pageLoaded.value = true })
  const access = route.query.access_token as string
  const refresh = route.query.refresh_token as string
  if (access && refresh) {
    auth.setTokens(access, refresh)
    auth.tryFetchProfile().then(ok => { if (ok) router.replace("/landing") })
  }
})

function clearCooldownTimer() {
  if (cooldownTimer.value) { window.clearInterval(cooldownTimer.value); cooldownTimer.value = null }
}
function startCooldown(seconds: number) {
  cooldown.value = seconds; clearCooldownTimer()
  cooldownTimer.value = window.setInterval(() => {
    cooldown.value -= 1
    if (cooldown.value <= 0) clearCooldownTimer()
  }, 1000)
}

const rules: FormRules = {
  account: [{ required: true, message: "请输入手机号或邮箱", trigger: "blur" }],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 8, max: 64, message: "密码长度 8-64 位", trigger: "blur" },
    { validator: (_r: any, v: string, cb: any) => { if (v && !(/\d/.test(v) && /[a-zA-Z]/.test(v))) cb(new Error("密码必须包含字母和数字")); else cb() }, trigger: "blur" },
  ],
  nickname: [{ validator: (_r: any, v: string, cb: any) => { if (isLogin.value) return cb(); if (!v?.trim()) cb(new Error("请输入用户名")); else if (v.trim().length < 2) cb(new Error("用户名至少2个字符")); else cb() }, trigger: "blur" }],
}

async function sendSms() {
  if (!isPhoneAccount.value) { ElMessage.warning("请输入正确的手机号"); return }
  smsLoading.value = true
  try {
    const { default: api } = await import("@/api/client")
    await api.post("/auth/sms/send-code", { phone: form.account.trim(), scene: "login" })
    ElMessage.success("验证码已发送")
    startCooldown(60)
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "发送失败") }
  finally { smsLoading.value = false }
}

async function handleSubmit() {
  if (mode.value === "sms" && isLogin.value) {
    await smsLogin()
    return
  }
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true; errorMsg.value = ""
  try {
    if (isLogin.value) {
      await auth.login(form.account, form.password)
      router.replace((route.query.redirect as string) || "/landing")
    } else {
      const body: any = { password: form.password, nickname: form.nickname?.trim() }
      if (isPhoneAccount.value) body.phone = form.account.trim()
      else body.email = form.account.trim()
      const { default: api } = await import("@/api/client")
      await api.post("/auth/register", body)
      await auth.login(form.account, form.password)
      router.replace("/home?new_user=1")
    }
  } catch (e: any) {
    const resp = e.response
    if (!resp) errorMsg.value = "网络连接失败，请确认后端已启动"
    else if (resp.status === 500) errorMsg.value = "服务器内部错误"
    else {
      const d = resp.data?.detail
      errorMsg.value = Array.isArray(d) ? d.map((x: any) => x.msg || JSON.stringify(x)).join("；") : (typeof d === "string" ? d : `请求失败 (${resp.status})`)
    }
  } finally { loading.value = false }
}

async function smsLogin() {
  if (!form.account.trim() || !form.smsCode.trim()) { ElMessage.warning("请填写手机号和验证码"); return }
  loading.value = true; errorMsg.value = ""
  try {
    await auth.loginWithSms(form.account.trim(), form.smsCode.trim())
    if (auth.needSetup) {
      showSetup.value = true
    } else {
      router.replace((route.query.redirect as string) || "/landing")
    }
  } catch (e: any) {
    const resp = e.response
    if (!resp) errorMsg.value = "网络连接失败，请确认后端已启动"
    else {
      const d = resp.data?.detail
      errorMsg.value = Array.isArray(d) ? d.map((x: any) => x.msg || JSON.stringify(x)).join("；") : (typeof d === "string" ? d : `请求失败 (${resp.status})`)
    }
  }
  finally { loading.value = false }
}

async function doSetup() {
  setupError.value = ""
  if (!setupForm.nickname.trim() || setupForm.nickname.trim().length < 2) { setupError.value = "用户名至少2个字符"; return }
  if (setupForm.password !== setupForm.confirmPassword) { setupError.value = "两次密码不一致"; return }
  if (!(/\d/.test(setupForm.password) && /[a-zA-Z]/.test(setupForm.password))) { setupError.value = "密码必须包含字母和数字"; return }
  if (setupForm.password.length < 8) { setupError.value = "密码长度至少8位"; return }
  setupLoading.value = true
  try {
    await auth.setupAccount(setupForm.password, setupForm.nickname.trim())
    ElMessage.success("设置完成，欢迎使用律镜！")
    router.replace((route.query.redirect as string) || "/landing")
  } catch (e: any) {
    setupError.value = e?.response?.data?.detail || "设置失败，请重试"
  } finally { setupLoading.value = false }
}

function switchMode() { isLogin.value = !isLogin.value; errorMsg.value = ""; formRef.value?.resetFields() }
</script>

<template>
  <div class="login-page" :class="{ loaded: pageLoaded }">
    <Plasma color="#2F65FF" :speed="1.6" :scale="1.6" :opacity="0.8" :mouse-interactive="true" />
    <div class="bg-noise"></div>
    <div class="bg-grid"></div>
    <div class="bg-accent"></div>

    <!-- 左侧品牌区 -->
    <div class="brand-panel">
      <div class="brand-content">
        <div class="brand-mark">
          <span class="brand-icon">&#x2696;</span>
          <div class="brand-ring"></div>
        </div>
        <h1 class="brand-name">律 镜</h1>
        <p class="brand-tagline">以数为镜，洞察裁判之律</p>
        <div class="brand-features">
          <span>智能类案检索</span>
          <span class="dot">·</span>
          <span>裁判规则分析</span>
          <span class="dot">·</span>
          <span>AI 深度问答</span>
        </div>
      </div>
      <p class="brand-footer">© 2026 LawMirror</p>
    </div>

    <!-- 右侧表单区 -->
    <div class="form-panel">
      <div class="form-card">
        <!-- 设置密码 & 用户名（短信注册后） -->
        <template v-if="showSetup">
          <div class="form-tabs">
            <button class="active">设置账号</button>
            <div class="tab-indicator" style="transform:translateX(0)"></div>
          </div>
          <p class="setup-hint">手机号 {{ form.account }} 验证通过，请设置密码和用户名</p>
          <div v-if="setupError" class="form-error">{{ setupError }}</div>
          <el-form @submit.prevent="doSetup" size="large" label-position="top">
            <el-form-item label="用户名">
              <el-input v-model="setupForm.nickname" placeholder="给自己取个名字（不可重复）" :prefix-icon="User" maxlength="20" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="setupForm.password" type="password" placeholder="8-64位，需包含字母和数字" :prefix-icon="Lock" show-password />
            </el-form-item>
            <el-form-item label="确认密码">
              <el-input v-model="setupForm.confirmPassword" type="password" placeholder="再次输入密码" :prefix-icon="Lock" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" native-type="submit" :loading="setupLoading" class="submit-btn">
                {{ setupLoading ? '设置中...' : '完成设置' }}
              </el-button>
            </el-form-item>
          </el-form>
        </template>

        <!-- 登录 / 注册 -->
        <template v-else>
        <div class="form-tabs">
          <button :class="{ active: isLogin }" @click="isLogin = true; errorMsg = ''">登录</button>
          <button :class="{ active: !isLogin }" @click="isLogin = false; errorMsg = ''">注册</button>
          <div class="tab-indicator" :style="{ transform: isLogin ? 'translateX(0)' : 'translateX(100%)' }"></div>
        </div>

        <!-- 登录方式切换 -->
        <div class="login-mode-switch" v-if="isLogin">
          <span :class="{ on: mode === 'password' }" @click="mode = 'password'; errorMsg = ''">密码登录</span>
          <span :class="{ on: mode === 'sms' }" @click="mode = 'sms'; errorMsg = ''">验证码登录</span>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleSubmit" size="large" label-position="top">
          <!-- 错误提示 -->
          <div v-if="errorMsg" class="form-error">{{ errorMsg }}</div>

          <el-form-item prop="account" :label="isLogin && mode === 'sms' ? '手机号' : '账号'">
            <el-input v-model="form.account" :placeholder="isLogin ? '手机号或邮箱' : '手机号 或 邮箱地址'" :prefix-icon="Message" clearable />
          </el-form-item>

          <el-form-item v-if="!(isLogin && mode === 'sms')" prop="password" label="密码">
            <el-input v-model="form.password" type="password" placeholder="8-64位，需包含字母和数字" :prefix-icon="Lock" show-password />
          </el-form-item>

          <el-form-item v-if="isLogin && mode === 'sms'" prop="smsCode" label="验证码">
            <div class="sms-row">
              <el-input v-model="form.smsCode" placeholder="短信验证码" :prefix-icon="Message" />
              <el-button :disabled="cooldown > 0 || !isPhoneAccount" :loading="smsLoading" @click="sendSms" class="sms-btn">
                {{ cooldown > 0 ? `${cooldown}s` : "获取验证码" }}
              </el-button>
            </div>
          </el-form-item>

          <el-form-item v-if="!isLogin" prop="confirmPassword" label="确认密码">
            <el-input v-model="form.confirmPassword" type="password" placeholder="再次输入密码" :prefix-icon="Lock" show-password />
          </el-form-item>
          <el-form-item v-if="!isLogin" prop="nickname" label="用户名 *" required>
            <el-input v-model="form.nickname" placeholder="给自己取个名字（必填，不可重复）" :prefix-icon="User" maxlength="20" />
          </el-form-item>

          <el-form-item>
            <button type="submit" :disabled="loading" class="submit-btn">
              <span v-if="loading" class="submit-loading">处理中...</span>
              <template v-else>
                <span class="submit-text">{{ isLogin ? "登 录" : "注 册 并 登 录" }}</span>
                <span class="submit-arrow">
                  <svg height="24" width="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M0 0h24v24H0z" fill="none"></path><path d="M16.172 11l-5.364-5.364 1.414-1.414L20 12l-7.778 7.778-1.414-1.414L16.172 13H4v-2z" fill="currentColor"></path></svg>
                </span>
              </template>
            </button>
          </el-form-item>
        </el-form>

        </template>

        <div class="switch-row" v-if="!showSetup">
          <span v-if="isLogin">还没有账号？</span>
          <span v-else>已有账号？</span>
          <span class="switch-link" @click="switchMode">{{ isLogin ? "立即注册" : "去登录" }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ========== 全局布局 ========== */
.login-page {
  display: flex; min-height: 100vh; background: #0D1117;
  position: relative; overflow: hidden;
}
.login-page.loaded .brand-content { animation: fadeSlideUp 0.8s cubic-bezier(0.22,1,0.36,1) both; }
.login-page.loaded .form-card { animation: fadeSlideUp 0.8s 0.15s cubic-bezier(0.22,1,0.36,1) both; }
.login-page.loaded .bg-accent { animation: breathe 6s ease-in-out infinite; }

@keyframes fadeSlideUp { from { opacity: 0; transform: translateY(32px); } to { opacity: 1; transform: translateY(0); } }
@keyframes breathe { 0%,100% { opacity: 0.25; } 50% { opacity: 0.45; } }

/* ========== 背景层 ========== */
.bg-noise {
  position: absolute; inset: 0; opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}
.bg-grid {
  position: absolute; inset: 0; opacity: 0.06;
  background-image: linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 64px 64px;
}
.bg-accent {
  position: absolute; top: -20%; right: -10%; width: 600px; height: 600px;
  background: radial-gradient(circle, rgba(47,101,255,0.12) 0%, transparent 70%);
  border-radius: 50%; pointer-events: none;
}

/* ========== 左侧品牌 ========== */
.brand-panel {
  flex: 0 0 46%; display: flex; flex-direction: column;
  justify-content: center; align-items: center; position: relative; z-index: 2;
  background: rgba(13,17,23,0.5); backdrop-filter: blur(12px);
}
.brand-content { text-align: center; }
.brand-mark { position: relative; display: inline-block; margin-bottom: 20px; }
.brand-icon { font-size: 56px; filter: drop-shadow(0 0 20px rgba(47,101,255,0.3)); display: block; }
.brand-ring {
  position: absolute; inset: -16px; border-radius: 50%;
  border: 1px solid rgba(47,101,255,0.15);
  animation: breathe 4s ease-in-out infinite;
}
.brand-name {
  font-family: "PingFang SC", "Noto Serif SC", "SimSun", serif;
  font-size: 42px; font-weight: 200; letter-spacing: 0.25em;
  color: #F0F6FC; margin-bottom: 10px;
}
.brand-tagline {
  font-size: 14px; color: #484F58; letter-spacing: 0.08em;
  margin-bottom: 28px;
}
.brand-features { font-size: 12px; color: #8B949E; letter-spacing: 0.04em; display: flex; gap: 8px; justify-content: center; }
.brand-features .dot { color: #30363D; }
.brand-footer {
  position: absolute; bottom: 32px; font-size: 11px; color: #30363D;
  letter-spacing: 0.06em;
}

/* ========== 右侧表单 ========== */
.form-panel {
  flex: 1; display: flex; align-items: center; justify-content: center;
  background: rgba(22,27,34,0.55); backdrop-filter: blur(16px);
  position: relative; z-index: 2;
  border-left: 1px solid #30363D;
}
.form-card {
  width: 400px; max-width: 90%; padding: 48px 40px;
  background: #0D1117; border: 1px solid #21262D;
  border-radius: 2px;
}
.form-tabs {
  display: flex; position: relative; margin-bottom: 32px;
  border-bottom: 1px solid #21262D;
}
.form-tabs button {
  flex: 1; background: none; border: none; color: #484F58;
  font-size: 15px; padding: 10px 0; cursor: pointer; position: relative; z-index: 1;
  transition: color 0.25s; font-family: inherit;
}
.form-tabs button.active { color: #F0F6FC; }
.tab-indicator {
  position: absolute; bottom: -1px; left: 0; width: 50%; height: 2px;
  background: #2F65FF; transition: transform 0.3s cubic-bezier(0.22,1,0.36,1);
}

.login-mode-switch {
  display: flex; justify-content: center; gap: 24px; margin-bottom: 24px; font-size: 13px;
}
.login-mode-switch span { color: #484F58; cursor: pointer; transition: color 0.2s; }
.login-mode-switch span.on { color: #2F65FF; }

.form-error {
  background: rgba(248,113,113,0.08); border: 1px solid rgba(248,113,113,0.2);
  color: #F87171; font-size: 13px; padding: 10px 14px; border-radius: 2px; margin-bottom: 10px;
}

.setup-hint {
  text-align: center; font-size: 13px; color: #8B949E;
  margin-bottom: 20px; line-height: 1.6;
}

.sms-row { display: flex; gap: 10px; }
.sms-row .el-input { flex: 1; }
.sms-btn { flex-shrink: 0; white-space: nowrap; }

.submit-btn {
  width: 100%; height: 46px; display: flex; align-items: center; justify-content: center;
  gap: 0; padding: 0; border-radius: 10px; border: none;
  overflow: hidden; background: #2F65FF; color: #fff; cursor: pointer;
  font-family: inherit; transition: background 0.2s; position: relative;
}
.submit-btn:hover { background: #1D4ED8; }
.submit-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.submit-text {
  font-size: 1.05em; font-weight: 700; letter-spacing: 0.15em;
  transform: translateX(10px); transition: transform 0.3s;
}
.submit-arrow {
  display: flex; align-items: center;
  transform: translateX(-24px); opacity: 0; transition: all 0.3s;
}
.submit-btn:hover .submit-text { transform: translateX(-4px); }
.submit-btn:hover .submit-arrow { transform: translateX(4px); opacity: 1; }
.submit-loading { font-size: 1.05em; font-weight: 700; letter-spacing: 0.15em; }

.switch-row { text-align: center; font-size: 13px; color: #484F58; padding-top: 12px; }
.switch-link { color: #2F65FF; cursor: pointer; font-weight: 500; transition: opacity 0.2s; margin-left: 2px; }
.switch-link:hover { opacity: 0.8; }

/* ========== 深色表单覆盖 ========== */
:deep(.el-form-item__label) { color: #8B949E !important; font-size: 12px; font-weight: 500; }
:deep(.el-input__wrapper) {
  background: #0D1117 !important; border: 1px solid #21262D !important;
  box-shadow: none !important; border-radius: 2px !important;
  transition: border-color 0.2s;
}
:deep(.el-input__wrapper:hover) { border-color: #30363D !important; }
:deep(.el-input__wrapper.is-focus) { border-color: #2F65FF !important; box-shadow: 0 0 0 3px rgba(47,101,255,0.12) !important; }
:deep(.el-input__inner) { color: #F0F6FC !important; }
:deep(.el-input__inner::placeholder) { color: #484F58 !important; }
:deep(.el-button--default) {
  background: #161B22 !important; border-color: #30363D !important; color: #8B949E !important;
  box-shadow: none !important; border-radius: 2px !important;
}
:deep(.el-button--default:hover) { border-color: #2F65FF !important; color: #F0F6FC !important; }

@media (max-width: 768px) {
  .brand-panel { display: none; }
  .form-panel { border-left: none; }
}
</style>