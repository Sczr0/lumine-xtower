<script>
  import { getImage, updateImage, listImages } from '../api.js';
  import { extractDominantColor } from '../lib/color.js';

  let { id: slug, onBack } = $props();

  let img = $state(null);
  let loading = $state(true);
  let saving = $state(false);
  let error = $state('');
  let saved = $state(false);

  let form = $state({
    game: '',
    characters: [],
    tags: [],
    dominant_color: '',
    hue: '',
    saturation: '',
    value: '',
    orientation: '',
    source_type: '',
    source_url: '',
    artist: '',
    authorization: '',
    is_ai: false,
    weight: 100,
    status: '',
    review_comment: '',
  });

  let navSlugs = $state([]);
  let currentIdx = $state(-1);

  const PRELOAD_AHEAD = 3;
  const PRELOAD_BEHIND = 1;
  const preloadCache = new Map();

  function applyFormData(data) {
    img = data;
    form = {
      game: data.game || '',
      characters: parseList(data.characters),
      tags: parseList(data.tags),
      dominant_color: data.dominant_color || '',
      hue: data.hue != null ? String(data.hue) : '',
      saturation: data.saturation != null ? String(data.saturation) : '',
      value: data.value != null ? String(data.value) : '',
      orientation: data.orientation || '',
      source_type: data.source_type || '',
      source_url: data.source_url || '',
      artist: data.artist || '',
      authorization: data.authorization || '',
      is_ai: data.is_ai || false,
      weight: data.weight ?? 100,
      status: data.status || '',
      review_comment: data.review_comment || '',
    };
  }

  function preloadImageFile(path) {
    const url = imgUrl(path);
    const image = new Image();
    image.src = url;
  }

  async function preloadOne(slug) {
    if (!slug || preloadCache.has(slug)) return;
    try {
      const data = await getImage(slug);
      preloadCache.set(slug, data);
      if (data.path) preloadImageFile(data.path);
    } catch {
      /* silently fail for preloads */
    }
  }

  function preloadAround() {
    if (navSlugs.length === 0 || currentIdx < 0) return;
    const start = Math.max(0, currentIdx - PRELOAD_BEHIND);
    const end = Math.min(navSlugs.length, currentIdx + PRELOAD_AHEAD + 1);
    for (let i = start; i < end; i++) {
      if (i !== currentIdx) {
        preloadOne(navSlugs[i]);
      }
    }
  }

  async function loadNavList(status) {
    try {
      const params = { per_page: 9999 };
      if (status) params.status = status;
      const data = await listImages(params);
      navSlugs = data.images.map(i => i.slug);
      currentIdx = navSlugs.indexOf(slug);
    } catch {}
  }

  function parseList(v) {
    if (!v) return [];
    if (Array.isArray(v)) return v;
    try { const p = JSON.parse(v); return Array.isArray(p) ? p : []; }
    catch { return []; }
  }

  async function load() {
    error = ''; saved = false;

    const cached = preloadCache.get(slug);
    if (cached) {
      applyFormData(cached);
      currentIdx = navSlugs.indexOf(slug);
      loading = false;
      preloadAround();
      return;
    }

    loading = true;
    try {
      const data = await getImage(slug);
      preloadCache.set(slug, data);
      applyFormData(data);
      loadNavList(data.status);
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
      preloadAround();
    }
  }

  function autoExtractColor() {
    const el = document.querySelector('.preview img');
    if (el && el.complete && el.naturalWidth > 0) {
      const color = extractDominantColor(el);
      if (color) form.dominant_color = color;
    }
  }

  // ── 标签输入 ──
  let charInput = $state(null);
  let tagInput = $state(null);

  function addTag(field, inputEl) {
    if (!inputEl) return;
    const value = inputEl.value.trim();
    if (!value) return;
    if (!form[field].includes(value)) {
      form[field] = [...form[field], value];
    }
    inputEl.value = '';
    inputEl.focus();
  }

  function removeTag(field, value) {
    form[field] = form[field].filter(v => v !== value);
  }

  function handleTagKey(e, field) {
    if (e.key === 'Enter') {
      e.preventDefault();
      const inputEl = field === 'characters' ? charInput : tagInput;
      addTag(field, inputEl);
    } else if (e.key === 'Backspace') {
      const inputEl = field === 'characters' ? charInput : tagInput;
      if (inputEl && inputEl.value === '' && form[field].length > 0) {
        removeTag(field, form[field][form[field].length - 1]);
      }
    }
  }

  // ── 保存 ──

  async function save() {
    saving = true; saved = false; error = '';
    try {
      const payload = {
        game: form.game || undefined,
        characters: JSON.stringify(form.characters),
        tags: JSON.stringify(form.tags),
        dominant_color: form.dominant_color || null,
        hue: form.hue ? parseInt(form.hue) : null,
        saturation: form.saturation ? parseInt(form.saturation) : null,
        value: form.value ? parseInt(form.value) : null,
        orientation: form.orientation || undefined,
        source_type: form.source_type || undefined,
        source_url: form.source_url || null,
        artist: form.artist || null,
        authorization: form.authorization || undefined,
        weight: form.weight || undefined,
        status: form.status || undefined,
        review_comment: form.review_comment || null,
      };
      if (form.is_ai) payload.is_ai = true;

      const clean = {};
      for (const [k, v] of Object.entries(payload)) {
        if (v !== undefined) clean[k] = v;
      }
      await updateImage(slug, clean);
      saved = true;
      setTimeout(() => saved = false, 2000);
      if (form.status && form.status !== img.status) {
        img = { ...img, status: form.status };
      }
      preloadCache.delete(slug);
    } catch (e) {
      error = e.message;
    } finally {
      saving = false;
    }
  }

  async function quickApprove() {
    form.status = 'approved';
    await save();
    goNext();
  }

  async function quickReject() {
    form.status = 'rejected';
    await save();
    goNext();
  }

  function goNext() {
    if (currentIdx < navSlugs.length - 1) {
      slug = navSlugs[currentIdx + 1];
      load();
    }
  }

  function goPrev() {
    if (currentIdx > 0) {
      slug = navSlugs[currentIdx - 1];
      load();
    }
  }

  async function nextImage() {
    await save();
    goNext();
  }

  async function prevImage() {
    await save();
    goPrev();
  }

  function handleKey(e) {
    // 焦点在 input/select/textarea 时不触发全局快捷键
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    switch (e.key) {
      case 'ArrowLeft': e.preventDefault(); prevImage(); break;
      case 'ArrowRight': e.preventDefault(); nextImage(); break;
      case 's': case 'S': e.preventDefault(); save(); break;
      case 'a': case 'A': e.preventDefault(); quickApprove(); break;
      case 'r': case 'R': e.preventDefault(); quickReject(); break;
      case 'Escape': e.preventDefault(); onBack(); break;
    }
  }

  $effect(() => {
    load();
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  });

  const IMAGE_BASE = import.meta.env.VITE_IMAGE_BASE || 'https://lumine-images.xtower.site';
  function imgUrl(p) { return `${IMAGE_BASE}/${p}`; }
</script>

<div class="editor">
  {#if loading}
    <div class="loading">加载中...</div>
  {:else if error}
    <div class="error-bar">
      <span>{error}</span>
      <button onclick={load}>重试</button>
    </div>
  {:else if img}
    <div class="layout">
      <div class="preview">
        <div class="img-wrap" style="background: {img.dominant_color || '#e5e7eb'}">
          <img src={imgUrl(img.path)} alt={img.slug} />
        </div>
        <div class="img-meta">
          <span class="badge status-{img.status}">{img.status}</span>
          <code>{img.slug}</code>
          <span>{img.width}×{img.height} · {(img.file_size / 1024).toFixed(0)}KB</span>
          {#if img.hue != null}
            <span class="hue-dot" style="background: hsl({img.hue}, 70%, 50%)"></span>
            <span>H{img.hue}°</span>
          {/if}
        </div>
      </div>

      <div class="form">
        <div class="form-row">
          <div class="field">
            <label>游戏</label>
            <select bind:value={form.game}>
              <option value="genshin">原神</option>
              <option value="hsr">星穹铁道</option>
              <option value="zzz">绝区零</option>
              <option value="honkai3">崩坏3</option>
            </select>
          </div>
          <div class="field">
            <label>方向</label>
            <select bind:value={form.orientation}>
              <option value="landscape">横图</option>
              <option value="portrait">竖图</option>
              <option value="square">方形</option>
            </select>
          </div>
        </div>

        <!-- 标签输入：角色 -->
        <div class="field">
          <label>角色 <button class="btn-sm" onclick={() => form.characters = []}>清除</button></label>
          <div class="tag-input" role="listbox" aria-label="角色标签">
            {#each form.characters as tag, i (tag)}
              <span class="tag">
                {tag}
                <button class="tag-x" onclick={() => removeTag('characters', tag)} aria-label="删除">&times;</button>
              </span>
            {/each}
            <input
              class="tag-field"
              placeholder="输入角色名，回车添加"
              bind:this={charInput}
              onkeydown={(e) => handleTagKey(e, 'characters')}
            />
          </div>
        </div>

        <!-- 标签输入：通用标签 -->
        <div class="field">
          <label>标签 <button class="btn-sm" onclick={() => form.tags = []}>清除</button></label>
          <div class="tag-input" role="listbox" aria-label="通用标签">
            {#each form.tags as tag, i (tag)}
              <span class="tag">
                {tag}
                <button class="tag-x" onclick={() => removeTag('tags', tag)} aria-label="删除">&times;</button>
              </span>
            {/each}
            <input
              class="tag-field"
              placeholder="输入标签，回车添加"
              bind:this={tagInput}
              onkeydown={(e) => handleTagKey(e, 'tags')}
            />
          </div>
        </div>

        <div class="field">
          <label>主色调 <button class="btn-sm" onclick={autoExtractColor}>自动提取</button></label>
          <div class="color-row">
            <span class="color-swatch" style="background: {form.dominant_color || '#fff'}"></span>
            <input bind:value={form.dominant_color} placeholder="#6366f1" />
          </div>
        </div>

        <div class="form-row">
          <div class="field">
            <label>色相 H (0-360)</label>
            <input type="number" bind:value={form.hue} min="0" max="360" placeholder="210" />
          </div>
          <div class="field">
            <label>饱和度 S (0-100)</label>
            <input type="number" bind:value={form.saturation} min="0" max="100" placeholder="70" />
          </div>
          <div class="field">
            <label>明度 V (0-100)</label>
            <input type="number" bind:value={form.value} min="0" max="100" placeholder="80" />
          </div>
        </div>

        <div class="field">
          <label>来源类型</label>
          <select bind:value={form.source_type}>
            <option value="official">官方</option>
            <option value="pixiv">Pixiv</option>
            <option value="twitter">Twitter</option>
            <option value="manual">手动</option>
            <option value="submission">投稿</option>
          </select>
        </div>

        <div class="form-row">
          <div class="field">
            <label>来源链接</label>
            <input bind:value={form.source_url} placeholder="https://" />
          </div>
          <div class="field">
            <label>画师 <input bind:value={form.artist} placeholder="画师名" /></label>
          </div>
        </div>

        <div class="form-row">
          <div class="field">
            <label>授权状态 <select bind:value={form.authorization}>
              <option value="official">官方授权</option>
              <option value="submitted">投稿授权</option>
              <option value="unknown">未确认</option>
            </select></label>
          </div>
          <div class="field">
            <label>权重 <input type="number" bind:value={form.weight} min="0" max="999" /></label>
          </div>
        </div>

        <div class="form-row">
          <div class="field checkbox">
            <label>
              <input type="checkbox" bind:checked={form.is_ai} />
              AI 生成
            </label>
          </div>
          <div class="field">
            <label>审核备注 <input bind:value={form.review_comment} placeholder="驳回原因等" /></label>
          </div>
        </div>

        <div class="status-row">
          {#if form.hue}
            <span class="hue-bar" style="background: linear-gradient(to right, hsl({form.hue}, 100%, 50%), hsl({(parseInt(form.hue) + 30) % 360}, 100%, 50%))"></span>
          {/if}
          <span class="badge status-{img.status}">{img.status}</span>
        </div>

        <div class="actions">
          <button class="btn btn-approve" onclick={quickApprove}>批准 (A)</button>
          <button class="btn btn-reject" onclick={quickReject}>驳回 (R)</button>
          <button class="btn btn-save" onclick={save} disabled={saving}>
            {saving ? '保存中...' : '保存 (S)'}
          </button>
          <button class="btn btn-back" onclick={onBack}>返回 (Esc)</button>
          <div class="nav-btns">
            <button class="btn btn-nav" onclick={prevImage}>← 上张</button>
            <button class="btn btn-nav" onclick={nextImage}>下张 →</button>
          </div>
        </div>

        {#if saved}
          <div class="toast">已保存</div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .loading { text-align: center; padding: 3rem; color: #9ca3af; }
  .error-bar {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.75rem 1rem; background: #fef2f2; border-radius: 8px;
    color: #dc2626;
  }
  .error-bar button { padding: 0.25rem 0.75rem; border: 1px solid #dc2626; border-radius: 4px; background: #fff; cursor: pointer; }

  .layout { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }

  .img-wrap { border-radius: 8px; overflow: hidden; display: flex; align-items: center; justify-content: center; max-height: 70vh; }
  .img-wrap img { max-width: 100%; max-height: 70vh; object-fit: contain; }

  .img-meta {
    display: flex; align-items: center; gap: 0.75rem;
    margin-top: 0.5rem; font-size: 0.8rem; color: #6b7280; flex-wrap: wrap;
  }
  .img-meta code { font-size: 0.75rem; }
  .hue-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; border: 1px solid #d1d5db; }
  .badge { font-size: 0.65rem; padding: 1px 6px; border-radius: 10px; }
  .status-pending_review { background: #fef3c7; color: #92400e; }
  .status-approved { background: #d1fae5; color: #065f46; }
  .status-rejected { background: #fee2e2; color: #991b1b; }

  .form { display: flex; flex-direction: column; gap: 0.75rem; }
  .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
  .form-row:has(.checkbox) { grid-template-columns: auto 1fr; }

  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label { font-size: 0.75rem; font-weight: 600; color: #374151; }
  .field input, .field select {
    padding: 0.4rem 0.6rem; border: 1px solid #d1d5db; border-radius: 6px;
    font-size: 0.85rem;
  }
  /* label 嵌套 input/select 时保持上下排列 */
  label:has(> input), label:has(> select) {
    display: flex; flex-direction: column; gap: 0.25rem;
  }

  /* ── 标签输入 ── */
  .tag-input {
    display: flex; flex-wrap: wrap; gap: 4px; align-items: center;
    padding: 4px 6px; border: 1px solid #d1d5db; border-radius: 6px;
    background: #fff; min-height: 34px; cursor: text;
  }
  .tag-input:focus-within {
    border-color: #6366f1; box-shadow: 0 0 0 2px rgba(99,102,241,0.15);
  }
  .tag {
    display: inline-flex; align-items: center; gap: 2px;
    padding: 1px 6px; background: #eef2ff; color: #4338ca;
    border-radius: 4px; font-size: 0.78rem; line-height: 1.6;
  }
  .tag-x {
    background: none; border: none; cursor: pointer;
    font-size: 1rem; line-height: 1; color: #6366f1; padding: 0 1px;
  }
  .tag-x:hover { color: #dc2626; }
  .tag-field {
    flex: 1; min-width: 80px; border: none !important;
    outline: none; padding: 2px 4px; font-size: 0.85rem;
  }

  .checkbox label { display: flex; align-items: center; gap: 0.4rem; cursor: pointer; }
  .checkbox input { width: auto; }

  .color-row { display: flex; gap: 0.5rem; align-items: center; }
  .color-swatch { width: 32px; height: 32px; border-radius: 6px; border: 1px solid #d1d5db; flex-shrink: 0; }

  .btn-sm {
    font-size: 0.7rem; padding: 1px 6px; border: 1px solid #d1d5db;
    border-radius: 4px; background: #fff; cursor: pointer; margin-left: 0.5rem;
  }
  .btn-sm:hover { background: #f3f4f6; }

  .status-row { display: flex; align-items: center; gap: 0.5rem; }
  .hue-bar { height: 6px; flex: 1; border-radius: 3px; }

  .actions {
    display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
    margin-top: 0.5rem;
  }
  .btn {
    padding: 0.5rem 1rem; border: none; border-radius: 6px;
    font-size: 0.85rem; cursor: pointer; font-weight: 500;
  }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-approve { background: #059669; color: #fff; }
  .btn-approve:hover:not(:disabled) { background: #047857; }
  .btn-reject { background: #dc2626; color: #fff; }
  .btn-reject:hover:not(:disabled) { background: #b91c1c; }
  .btn-save { background: #6366f1; color: #fff; }
  .btn-save:hover:not(:disabled) { background: #4f46e5; }
  .btn-back { background: #e5e7eb; color: #374151; }
  .btn-back:hover:not(:disabled) { background: #d1d5db; }
  .btn-nav { background: #fff; border: 1px solid #d1d5db; color: #374151; }
  .btn-nav:hover:not(:disabled) { background: #f3f4f6; }
  .nav-btns { display: flex; gap: 0.25rem; margin-left: auto; }

  .toast {
    position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
    background: #059669; color: #fff; padding: 0.5rem 1rem; border-radius: 8px;
    font-size: 0.85rem; animation: fadeIn 0.2s;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateX(-50%) translateY(10px); } }

  @media (max-width: 1024px) {
    .layout { grid-template-columns: 1fr; }
  }
</style>
