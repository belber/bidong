const EXPORT_KINDS = ['subtitle', 'danmaku', 'comment', 'audio'];

function initialExports() {
  const exports = {};
  EXPORT_KINDS.forEach((kind) => {
    exports[kind] = { state: 'idle', progress: 0, sizeText: '', path: '' };
  });
  return exports;
}

function cloneItem(item) {
  return Object.assign({}, item);
}

function beginExport(exports, kind) {
  const next = Object.assign({}, exports);
  next[kind] = Object.assign(cloneItem(exports[kind]), {
    state: 'downloading',
    progress: 0,
    sizeText: ''
  });
  return next;
}

function updateExportProgress(exports, kind, progress, sizeText) {
  const next = Object.assign({}, exports);
  next[kind] = Object.assign(cloneItem(exports[kind]), {
    progress: Math.max(0, Math.min(100, progress || 0)),
    sizeText: sizeText || ''
  });
  return next;
}

function completeExport(exports, kind, path) {
  const next = Object.assign({}, exports);
  next[kind] = Object.assign(cloneItem(exports[kind]), {
    state: 'ready',
    progress: 100,
    sizeText: '',
    path
  });
  return next;
}

function failExport(exports, kind) {
  const next = Object.assign({}, exports);
  next[kind] = Object.assign(cloneItem(exports[kind]), {
    state: 'failed',
    progress: 0,
    sizeText: '',
    path: ''
  });
  return next;
}

function markExportSaved(exports, kind) {
  const next = Object.assign({}, exports);
  next[kind] = Object.assign(cloneItem(exports[kind]), { state: 'saved' });
  return next;
}

function exportLabel(item) {
  if (item.state === 'downloading') return item.progress + '%';
  if (item.state === 'ready') return '保存';
  if (item.state === 'saved') return '再次保存';
  if (item.state === 'failed') return '重试';
  return '下载';
}

module.exports = {
  EXPORT_KINDS,
  initialExports,
  beginExport,
  updateExportProgress,
  completeExport,
  failExport,
  markExportSaved,
  exportLabel
};
