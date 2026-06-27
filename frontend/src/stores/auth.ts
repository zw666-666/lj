import { defineStore } from "pinia"
import { ref, computed } from "vue"
import api from "@/api/client"

export interface UserProfile {
  id: number
  phone: string | null
  email: string | null
  nickname: string | null
  avatar_url: string | null
  role: string
  subscription_status: string  // free / premium / expired
  subscription_expires_at: string | null
  lifetime_export_count: number
}

export const useAuthStore = defineStore("auth", () => {
  const token = ref(sessionStorage.getItem("access_token") || "")
  const refreshToken = ref(sessionStorage.getItem("refresh_token") || "")
  const user = ref<UserProfile | null>(null)
  const switchingAccount = ref(false)  // 切换账号时不触发401跳转
  const needSetup = ref(false)  // 短信登录后需设置密码和用户名

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === "admin")
  const isPremium = computed(() =>
    user.value?.role === "admin" || user.value?.subscription_status === "premium"
  )
  const subscriptionStatus = computed(() => user.value?.subscription_status || "free")
  const subscriptionExpiresAt = computed(() => user.value?.subscription_expires_at || null)
  const exportRemaining = computed(() => {
    if (isPremium.value) return -1
    return Math.max(0, 2 - (user.value?.lifetime_export_count || 0))
  })

  async function login(account: string, password: string) {
    const res = await api.post("/auth/login", { account, password })
    setTokens(res.data.access_token, res.data.refresh_token)
    await fetchProfile()
  }

  async function loginWithSms(account: string, smsCode: string) {
    const res = await api.post("/auth/login", {
      account,
      sms_code: smsCode,
      login_type: "sms_code",
    })
    setTokens(res.data.access_token, res.data.refresh_token)
    needSetup.value = res.data.need_setup || false
    if (!needSetup.value) {
      await fetchProfile()
    } else {
      // 新用户暂不 fetch profile（nickname 是临时值），等 setup 后再取
      user.value = null
    }
  }

  async function setupAccount(password: string, nickname: string) {
    await api.post("/auth/setup", { password, nickname })
    needSetup.value = false
    await fetchProfile()
  }

  async function fetchProfile() {
    if (!token.value) return
    try {
      const res = await api.get("/auth/me")
      user.value = res.data
    } catch {
      logout()
    }
  }

  async function tryFetchProfile(): Promise<boolean> {
    if (!token.value) return false
    try {
      const res = await api.get("/auth/me")
      user.value = res.data
      return true
    } catch {
      return false
    }
  }

  function setTokens(access: string, refresh: string) {
    token.value = access
    refreshToken.value = refresh
    sessionStorage.setItem("access_token", access)
    sessionStorage.setItem("refresh_token", refresh)
  }

  function logout() {
    token.value = ""
    refreshToken.value = ""
    user.value = null
    sessionStorage.removeItem("access_token")
    sessionStorage.removeItem("refresh_token")
  }

  // 订阅到期相关计算
  const daysUntilExpiry = computed(() => {
    if (!user.value?.subscription_expires_at) return null
    const now = new Date()
    const exp = new Date(user.value.subscription_expires_at)
    return Math.ceil((exp.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  })

  return {
    token, refreshToken, user, isLoggedIn, isAdmin, isPremium,
    subscriptionStatus, subscriptionExpiresAt, exportRemaining, daysUntilExpiry,
    switchingAccount, needSetup,
    login, loginWithSms, setupAccount, fetchProfile, tryFetchProfile, setTokens, logout,
  }
})
