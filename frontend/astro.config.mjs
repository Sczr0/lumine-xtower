import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://lumine.xtower.site',
  output: 'static',
  build: {
    assets: '_assets',
  },
  integrations: [sitemap()],
});
