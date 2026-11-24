import axios from 'axios'

export const http = axios.create({ baseURL: '/api', withCredentials: true, timeout: 18000 })

export function onSessionExpired(handler) {
  http.interceptors.response.use(undefined, (error) => {
    if (error.response?.status === 401 && !['/auth/login', '/auth/register', '/auth/me'].includes(error.config?.url)) {
      handler()
    }
    return Promise.reject(error)
  })
}

export const get = async (url, params) => (await http.get(url, { params })).data.data
export const post = async (url, payload = {}) => (await http.post(url, payload)).data.data
export const put = async (url, payload) => (await http.put(url, payload)).data.data
export const remove = async (url) => (await http.delete(url)).data.data

export function errorText(error) {
  const message = error.response?.data?.msg
  if (message) return message
  const method = error.config?.method?.toLowerCase()
  const path = error.config?.url || ''
  const changesData = ['post', 'put', 'patch', 'delete'].includes(method)
    && !['/auth/login', '/auth/logout'].includes(path) && !path.endsWith('/explain')
  if (changesData && (!error.response || error.response.status >= 500)) {
    return '暂无法确认写入结果，请先刷新对应列表或页面，核对数据后再决定是否重试。'
  }
  return '无法完成请求，请检查服务连接后重试。'
}

export async function fetchAll(url, params) {
  const result = []
  const pageSize = 100
  for (let page = 1; ; page += 1) {
    const data = await get(url, { ...params, page, page_size: pageSize })
    result.push(...data.items)
    if (page * pageSize >= data.total || !data.items.length) return result
  }
}
