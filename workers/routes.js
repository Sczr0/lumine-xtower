/**
 * Cloudflare Workers 路由脚本
 *
 * 部署: wrangler deploy routes.js
 * 绑定 Pages 项目: 在 Cloudflare Dashboard 中将此 Worker 关联到 lumine.xtower.site
 *
 * 路由规则:
 *   /v1/*    → VPS (Rust API)
 *   /admin/* → VPS (Rust API, 由 CF Access 保护)
 *   /*       → Pages 静态资源
 */

// 替换为你的 VPS IP 或域名
const VPS_ORIGIN = 'http://your-vps-ip:3000';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // API 请求 → VPS
    if (path.startsWith('/v1/') || path.startsWith('/admin/')) {
      const target = new URL(VPS_ORIGIN);
      target.pathname = path;
      target.search = url.search;

      // 保留原始请求头（CF-Connecting-IP 等 CF 头会自动加上）
      return fetch(target.toString(), {
        method: request.method,
        headers: request.headers,
        body: request.method === 'GET' || request.method === 'HEAD'
          ? null : request.body,
      });
    }

    // 其余 → Pages 静态资源
    return env.ASSETS.fetch(request);
  },
};
