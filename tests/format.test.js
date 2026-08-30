const { formatDuration, formatMonth, formatDateTime } = require('../miniprogram/utils/format.js');

describe('formatDuration', () => {
  test('秒数格式化为 MM:SS', () => {
    expect(formatDuration(65)).toBe('01:05');
    expect(formatDuration(0)).toBe('00:00');
  });

  test('超过一小时格式化为 HH:MM:SS', () => {
    expect(formatDuration(3661)).toBe('01:01:01');
  });

  test('非法输入兜底为 00:00', () => {
    expect(formatDuration(undefined)).toBe('00:00');
    expect(formatDuration(-1)).toBe('00:00');
  });
});

describe('formatMonth / formatDateTime', () => {
  test('时间戳格式化为 YYYY-MM 与 YYYY-MM-DD HH:mm', () => {
    const ts = new Date(2026, 7, 30, 0, 55).getTime() / 1000;
    expect(formatMonth(ts)).toBe('2026-08');
    expect(formatDateTime(ts)).toBe('2026-08-30 00:55');
  });
});
