const {
  initialExports,
  beginExport,
  updateExportProgress,
  completeExport,
  failExport,
  markExportSaved,
  exportLabel
} = require('./exportState');

describe('on-demand export state', () => {
  test('starts all export items idle without downloading', () => {
    const exports = initialExports();
    expect(Object.keys(exports).sort()).toEqual(['audio', 'comment', 'danmaku', 'subtitle']);
    Object.values(exports).forEach((item) => {
      expect(item.state).toBe('idle');
      expect(item.progress).toBe(0);
      expect(item.path).toBe('');
    });
  });

  test('tracks downloading progress and disables tap', () => {
    let exports = beginExport(initialExports(), 'audio');
    expect(exports.audio.state).toBe('downloading');
    expect(exportLabel(exports.audio)).toBe('0%');
    exports = updateExportProgress(exports, 'audio', 42, '1.2 MB/2.8 MB');
    expect(exports.audio.state).toBe('downloading');
    expect(exports.audio.progress).toBe(42);
    expect(exports.audio.sizeText).toBe('1.2 MB/2.8 MB');
    expect(exportLabel(exports.audio)).toBe('42%');
  });

  test('becomes ready after successful download and saved after share', () => {
    let exports = completeExport(beginExport(initialExports(), 'subtitle'), 'subtitle', '/user/a.srt');
    expect(exports.subtitle.state).toBe('ready');
    expect(exportLabel(exports.subtitle)).toBe('保存');
    exports = markExportSaved(exports, 'subtitle');
    expect(exports.subtitle.state).toBe('saved');
    expect(exportLabel(exports.subtitle)).toBe('再次保存');
  });

  test('failed download can retry', () => {
    let exports = failExport(beginExport(initialExports(), 'comment'), 'comment', 'network');
    expect(exports.comment.state).toBe('failed');
    expect(exportLabel(exports.comment)).toBe('重试');
    exports = beginExport(exports, 'comment');
    expect(exports.comment.state).toBe('downloading');
  });
});
