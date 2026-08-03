import { createRouter, createWebHashHistory } from 'vue-router'
import api from '@/api/index'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'layout',
      component: () => import('../views/Layout.vue'),
    },
    {
      path: '/logs',
      name: 'log',
      component: () => import('../views/log.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/results',
      name: 'results',
      component: () => import('../views/Results.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/test',
      name: 'test',
      component: () => import('../views/Test.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/test1',
      name: 'test1',
      component: () => import('../views/Test1.vue'),
      meta: { requiresAdmin: true },
    },
  ],
})

router.beforeEach(async to => {
  if (!to.meta.requiresAdmin) return true
  try {const response = await api.getAuthStatus({});const status = response.data?.data;if (!status?.loginEnabled) return true;return status.authenticated && status.user?.role === 'admin' ? true : '/';} catch {return '/';}
})

export default router
