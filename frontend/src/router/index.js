import { createRouter, createWebHistory } from 'vue-router'
import Detect from '../views/Detect.vue'
import Report from '../views/Report.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/detect' },
    { path: '/detect', name: 'detect', component: Detect },
    { path: '/report', name: 'report', component: Report },
  ],
})
