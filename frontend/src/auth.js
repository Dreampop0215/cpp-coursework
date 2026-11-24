import { defineStore } from 'pinia'
import { get, post } from './api.js'

export const useAuth = defineStore('auth', {
  state: () => ({ user: null, known: false }),
  actions: {
    async restore() {
      if (this.known) return
      try {
        this.user = await get('/auth/me')
      } catch {
        this.user = null
      } finally {
        this.known = true
      }
    },
    async signIn(credentials) {
      this.user = await post('/auth/login', credentials)
      this.known = true
    },
    clear() {
      this.user = null
      this.known = true
    },
    async signOut() {
      await post('/auth/logout')
      this.clear()
    },
  },
})
