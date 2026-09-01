const { filterCards } = require('../miniprogram/utils/filter.js');

const cards = [
  { id: 'a', source: 'local', partition: '知识', title: '三体解析', up_name: '木鱼水心', tags: ['科幻'] },
  { id: 'b', source: 'robot', partition: '知识', title: '深度学习入门', up_name: '李沐', tags: ['AI'] },
  { id: 'c', source: 'robot', partition: '音乐', title: '夜的钢琴曲', up_name: '石进', tags: ['钢琴', '纯音乐'] }
];

describe('filterCards', () => {
  test('默认筛选返回全部', () => {
    expect(filterCards(cards, { source: 'all', partition: '全部', keyword: '' })).toEqual(cards);
  });

  test('按来源过滤', () => {
    const r = filterCards(cards, { source: 'robot', partition: '全部', keyword: '' });
    expect(r.map((c) => c.id)).toEqual(['b', 'c']);
  });

  test('按分区过滤', () => {
    const r = filterCards(cards, { source: 'all', partition: '知识', keyword: '' });
    expect(r.map((c) => c.id)).toEqual(['a', 'b']);
  });

  test('来源与分区叠加过滤', () => {
    const r = filterCards(cards, { source: 'robot', partition: '知识', keyword: '' });
    expect(r.map((c) => c.id)).toEqual(['b']);
  });

  test('关键字匹配标题', () => {
    expect(filterCards(cards, { source: 'all', partition: '全部', keyword: '三体' }).map((c) => c.id)).toEqual(['a']);
  });

  test('关键字匹配 UP主', () => {
    expect(filterCards(cards, { source: 'all', partition: '全部', keyword: '李沐' }).map((c) => c.id)).toEqual(['b']);
  });

  test('关键字匹配分区', () => {
    expect(filterCards(cards, { source: 'all', partition: '全部', keyword: '音乐' }).map((c) => c.id)).toEqual(['c']);
  });

  test('关键字匹配标签', () => {
    expect(filterCards(cards, { source: 'all', partition: '全部', keyword: '纯音乐' }).map((c) => c.id)).toEqual(['c']);
  });

  test('关键字大小写不敏感', () => {
    expect(filterCards(cards, { source: 'all', partition: '全部', keyword: 'ai' }).map((c) => c.id)).toEqual(['b']);
  });

  test('关键字含首尾空格时 trim 后再匹配', () => {
    expect(filterCards(cards, { source: 'all', partition: '全部', keyword: '  三体  ' }).map((c) => c.id)).toEqual(['a']);
  });

  test('无匹配返回空数组', () => {
    expect(filterCards(cards, { source: 'local', partition: '音乐', keyword: '' })).toEqual([]);
  });
});
