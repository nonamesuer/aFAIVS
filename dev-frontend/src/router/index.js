import { createRouter, createWebHashHistory } from 'vue-router'

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
    },
    {
      path: '/test',
      name: 'test',
      component: () => import('../views/Test.vue'),
    },
    {
      path: '/test1',
      name: 'test1',
      component: () => import('../views/Test1.vue'),
    },
  ],
})

export default router
