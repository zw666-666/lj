import { defineStore } from "pinia"
import { ref } from "vue"

export const useSearchStore = defineStore("search", () => {
  const refreshFlag = ref(0)  // 递增触发 Home 页面重新搜索

  function triggerRefresh() {
    refreshFlag.value++
  }

  return { refreshFlag, triggerRefresh }
})
