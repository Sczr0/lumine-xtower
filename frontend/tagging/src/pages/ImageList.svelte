<script>
  import { listImages, getStats } from '../api.js';

  let { onSelect } = $props();

  let images = $state([]);
  let total = $state(0);
  let stats = $state({ total: 0, pending_review: 0, approved: 0, rejected: 0 });
  let status = $state('');
  let page = $state(1);
  let loading = $state(true);
  let error = $state('');

  const perPage = 50;

  async function load() {
    loading = true; error = '';
    try {
      const q = { page, per_page: perPage };
      if (status) q.status = status;
      const data = await listImages(q);
      images = data.images;
      total = data.total;
      stats = await getStats();
    } catch (e) {
      error = e.message;
      images = [];
    } finally {
      loading = false;
    }
  }

  function filter(s) {
    status = s;
    page = 1;
    load();
  }

  function prevPage() { if (page > 1) { page--; load(); } }
  function nextPage() { if (page * perPage < total) { page++; load(); } }

  $effect(load);

  const totalPages = $derived(Math.ceil(total / perPage));

  const IMAGE_BASE = import.meta.env.VITE_IMAGE_BASE || 'https://lumine-images.xtower.site';
  function imgUrl(p) {
    return `${IMAGE_BASE}/${p}`;
  }
  function thumbUrl(img) {
    return imgUrl(img.thumbnail_path || img.path);
  }
</script>

<div class="toolbar">
  <div class="tabs">
    <button class:active={status === ''} onclick={() => filter('')}>
      全部 ({stats.total})
    </button>
    <button class:active={status === 'pending_review'} onclick={() => filter('pending_review')}>
      待审 ({stats.pending_review})
    </button>
    <button class:active={status === 'approved'} onclick={() => filter('approved')}>
      已通过 ({stats.approved})
    </button>
    <button class:active={status === 'rejected'} onclick={() => filter('rejected')}>
      已驳回 ({stats.rejected})
    </button>
  </div>
  <div class="pagination">
    <button disabled={page <= 1} onclick={prevPage}>←</button>
    <span>{page}/{totalPages || 1}</span>
    <button disabled={page * perPage >= total} onclick={nextPage}>→</button>
  </div>
</div>

{#if error}
  <div class="error">{error}</div>
{/if}

{#if loading}
  <div class="loading">加载中...</div>
{:else if images.length === 0}
  <div class="empty">暂无图片</div>
{:else}
  <div class="grid">
    {#each images as img}
      <button class="card" onclick={() => onSelect(img.slug)}>
        <div class="thumb" style="background: {img.dominant_color || '#e5e7eb'}">
          <img src={thumbUrl(img)} alt={img.slug} loading="lazy" />
        </div>
        <div class="info">
          <span class="id">{img.slug}</span>
          <span class="badge status-{img.status}">{img.status}</span>
        </div>
        <div class="meta">
          {img.orientation} · {img.width}×{img.height}
        </div>
      </button>
    {/each}
  </div>
{/if}

<style>
  .toolbar {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;
  }
  .tabs { display: flex; gap: 0.25rem; flex-wrap: wrap; }
  .tabs button {
    padding: 0.4rem 0.75rem; border: 1px solid #d1d5db;
    background: #fff; border-radius: 6px; cursor: pointer;
    font-size: 0.8rem; color: #374151;
  }
  .tabs button.active { background: #6366f1; color: #fff; border-color: #6366f1; }
  .tabs button:hover:not(.active) { background: #f3f4f6; }

  .pagination { display: flex; align-items: center; gap: 0.5rem; }
  .pagination button {
    padding: 0.3rem 0.6rem; border: 1px solid #d1d5db;
    background: #fff; border-radius: 4px; cursor: pointer;
  }
  .pagination button:disabled { opacity: 0.4; cursor: default; }
  .pagination span { font-size: 0.8rem; color: #6b7280; }

  .error { color: #dc2626; padding: 1rem; background: #fef2f2; border-radius: 8px; }
  .loading { text-align: center; color: #9ca3af; padding: 3rem; }
  .empty { text-align: center; color: #9ca3af; padding: 3rem; }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 1rem;
  }

  .card {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
    overflow: hidden; cursor: pointer; text-align: left;
    transition: box-shadow 0.15s;
  }
  .card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }

  .thumb {
    width: 100%; aspect-ratio: 16/9; overflow: hidden;
    display: flex; align-items: center; justify-content: center;
  }
  .thumb img {
    width: 100%; height: 100%; object-fit: cover;
  }

  .info {
    padding: 0.5rem; display: flex; justify-content: space-between;
    align-items: center; gap: 0.25rem;
  }
  .id { font-size: 0.75rem; color: #6b7280; font-family: monospace; }
  .badge {
    font-size: 0.65rem; padding: 1px 6px; border-radius: 10px;
    white-space: nowrap;
  }
  .status-pending_review { background: #fef3c7; color: #92400e; }
  .status-approved { background: #d1fae5; color: #065f46; }
  .status-rejected { background: #fee2e2; color: #991b1b; }

  .meta {
    padding: 0 0.5rem 0.5rem; font-size: 0.7rem; color: #9ca3af;
  }
</style>
