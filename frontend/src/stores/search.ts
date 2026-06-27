import { defineStore } from "pinia"
import { ref } from "vue"

export const useSearchStore = defineStore("search", () => {
  const currentQuery = ref("")
  const refreshFlag = ref(0)  // 递增触发 Home 页面重新搜索

  function setQuery(q: string) {
    currentQuery.value = q
  }

  function clearQuery() {
    currentQuery.value = ""
  }

  function triggerRefresh() {
    refreshFlag.value++
  }

  return { currentQuery, refreshFlag, setQuery, clearQuery, triggerRefresh }
})
