import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  base: '/tagging/',
  build: {
    outDir: '../../backend/static/tagging',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/admin': 'http://localhost:3000',
      '/v1': 'http://localhost:3000',
    },
  },
});
