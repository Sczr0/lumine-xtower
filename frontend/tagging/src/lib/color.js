/**
 * Canvas 主色调提取
 */
export function extractDominantColor(img) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  const size = 50;
  canvas.width = size;
  canvas.height = size;

  try {
    ctx.drawImage(img, 0, 0, size, size);
    const { data } = ctx.getImageData(0, 0, size, size);

    // 统计颜色直方图（量化到 4bit 精度）
    const colorMap = new Map();
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i] >> 4;
      const g = data[i + 1] >> 4;
      const b = data[i + 2] >> 4;
      const key = (r << 8) | (g << 4) | b;
      colorMap.set(key, (colorMap.get(key) || 0) + 1);
    }

    // 找出现最多的颜色
    let maxCount = 0;
    let dominantKey = 0;
    for (const [key, count] of colorMap) {
      if (count > maxCount) {
        maxCount = count;
        dominantKey = key;
      }
    }

    // 转回 8bit
    const r = ((dominantKey >> 8) & 0xf) * 17;
    const g = ((dominantKey >> 4) & 0xf) * 17;
    const b = (dominantKey & 0xf) * 17;

    return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
  } catch {
    return null;
  }
}

/**
 * 从 Canvas 像素数据中提取主色调（归一化到 8bit）
 */
export function extractFromCanvas(canvas) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  const size = 50;
  const smallCanvas = document.createElement('canvas');
  smallCanvas.width = size;
  smallCanvas.height = size;
  const smallCtx = smallCanvas.getContext('2d');
  if (!smallCtx) return null;

  smallCtx.drawImage(canvas, 0, 0, size, size);
  return extractDominantColor(smallCanvas);
}
