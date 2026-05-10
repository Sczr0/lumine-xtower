import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://lumine.xtower.site',
  output: 'static',
  build: {
    assets: '_assets',
  },
});
