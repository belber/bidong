const { filterCards } = require('../miniprogram/utils/filter.js');

const cards = [
  { id: 'a', source: 'local', tags: ['科幻'] },
  { id: 'b', source: 'robot', tags: ['科幻', '深度'] },
  { id: 'c', source: 'robot', tags: ['AI'] }
];

describe('filterCards', () => {
  test('source=all 且 tag=全部 返回全部', () => {
    expect(filterCards(cards, { source: 'all', tag: '全部' })).toEqual(cards);
  });

  test('按来源过滤', () => {
    const r = filterCards(cards, { source: 'robot', tag: '全部' });
    expect(r.map((c) => c.id)).toEqual(['b', 'c']);
  });

  test('按标签过滤（包含即命中）', () => {
    const r = filterCards(cards, { source: 'all', tag: '科幻' });
    expect(r.map((c) => c.id)).toEqual(['a', 'b']);
  });

  test('来源与标签叠加过滤', () => {
    const r = filterCards(cards, { source: 'robot', tag: '科幻' });
    expect(r.map((c) => c.id)).toEqual(['b']);
  });

  test('无匹配返回空数组', () => {
    expect(filterCards(cards, { source: 'local', tag: 'AI' })).toEqual([]);
  });
});
