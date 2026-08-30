const { groupByMonth } = require('../miniprogram/utils/group.js');

describe('groupByMonth', () => {
  test('空数组返回空数组', () => {
    expect(groupByMonth([])).toEqual([]);
  });

  test('按月份倒序分组，count 正确，组内按收藏时间倒序', () => {
    const cards = [
      { id: 'a', month: '2026-08', collected_at: 100 },
      { id: 'b', month: '2026-07', collected_at: 200 },
      { id: 'c', month: '2026-08', collected_at: 300 },
      { id: 'd', month: '2026-06', collected_at: 50 }
    ];
    const groups = groupByMonth(cards);
    expect(groups.map((g) => g.month)).toEqual(['2026-08', '2026-07', '2026-06']);
    expect(groups[0].count).toBe(2);
    expect(groups[0].items.map((c) => c.id)).toEqual(['c', 'a']);
  });

  test('缺少 month 字段的卡片跳过', () => {
    const groups = groupByMonth([{ id: 'x' }]);
    expect(groups).toEqual([]);
  });
});
