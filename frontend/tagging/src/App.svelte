<script>
  import ImageList from './pages/ImageList.svelte';
  import ImageEditor from './pages/ImageEditor.svelte';

  let page = $state('list');
  let selectedId = $state(null);

  function navigate(p, id) {
    page = p;
    selectedId = id || null;
    history.pushState(null, '', p === 'list' ? '/tagging' : `/tagging#id=${id}`);
  }

  // 浏览器前进后退
  function handlePop() {
    const hash = location.hash;
    if (hash.startsWith('#id=')) {
      page = 'edit';
      selectedId = hash.slice(4);
    } else {
      page = 'list';
      selectedId = null;
    }
  }

  $effect(() => {
    window.addEventListener('popstate', handlePop);
    return () => window.removeEventListener('popstate', handlePop);
  });
</script>

<div class="app">
  <header class="header">
    <div class="header-inner">
      <h1>
        <a href="/tagging" onclick={(e) => { e.preventDefault(); navigate('list'); }}>
          Lumine 打标台
        </a>
      </h1>
      <div class="shortcuts-hint">
        <kbd>←</kbd> <kbd>→</kbd> 翻页
        <kbd>S</kbd> 保存
        <kbd>A</kbd> 批准
        <kbd>R</kbd> 驳回
      </div>
    </div>
  </header>

  <main class="main">
    {#if page === 'list'}
      <ImageList onSelect={(id) => navigate('edit', id)} />
    {:else if page === 'edit'}
      <ImageEditor id={selectedId} onBack={() => navigate('list')} />
    {/if}
  </main>
</div>

<style>
  .app { min-height: 100vh; display: flex; flex-direction: column; }

  .header {
    background: #fff;
    border-bottom: 1px solid #e5e7eb;
    padding: 0.75rem 1.5rem;
    position: sticky; top: 0; z-index: 10;
  }
  .header-inner {
    max-width: 1400px; margin: 0 auto;
    display: flex; align-items: center; justify-content: space-between;
  }
  .header h1 { font-size: 1.1rem; }
  .header h1 a { color: #1f2937; text-decoration: none; }
  .header h1 a:hover { color: #6366f1; }

  .shortcuts-hint { font-size: 0.75rem; color: #9ca3af; }
  kbd {
    display: inline-block; padding: 1px 5px; font-size: 0.7rem;
    background: #f3f4f6; border: 1px solid #d1d5db;
    border-radius: 3px; margin: 0 1px;
  }

  .main { flex: 1; max-width: 1400px; width: 100%; margin: 0 auto; padding: 1.5rem; }
</style>
