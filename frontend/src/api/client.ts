import axios from "axios"
import { useAuthStore } from "@/stores/auth"

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api"

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
})

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401) {
      // 登录接口的 401 是密码错误，不是 token 过期，不拦截
      const url = error.config?.url || ""
      if (url.includes("/auth/login") || url.includes("/auth/sms/send-code")) {
        return Promise.reject(error)
      }
      const auth = useAuthStore()
      if (auth.switchingAccount) {
        return Promise.reject(error)
      }
      auth.logout()
      window.location.href = "/login"
    }
    if (error.response?.status === 402) {
      // 需要会员权限——跳转定价页
      const msg = error.response?.data?.detail || "该功能需要会员权限"
      import("element-plus").then(({ ElMessage }) => {
        ElMessage.warning(msg)
      })
      setTimeout(() => {
        window.location.href = "/pricing"
      }, 1500)
    }
    return Promise.reject(error)
  }
)

export default api
