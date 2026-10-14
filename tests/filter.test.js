const { filterCards, DOUYIN } = require('../miniprogram/utils/filter.js');

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

describe('平台筛选', () => {
  const mixed = [
    { id: 'b1', source: 'local', partition: '知识', title: 'B站一条', platform: 'bilibili', tags: [] },
    { id: 'd1', source: 'local', partition: '', title: '抖音一条', platform: 'douyin', tags: [] },
    { id: 'd2', source: 'robot', partition: '', title: '抖音两条', platform: 'douyin', tags: [] }
  ];

  test('选中「抖音」只看抖音卡片', () => {
    const r = filterCards(mixed, { source: 'all', partition: DOUYIN, keyword: '' });
    expect(r.map((c) => c.id)).toEqual(['d1', 'd2']);
  });

  test('选中 B站 分区时抖音卡片自然被排除', () => {
    const r = filterCards(mixed, { source: 'all', partition: '知识', keyword: '' });
    expect(r.map((c) => c.id)).toEqual(['b1']);
  });

  test('平台与来源筛选可叠加', () => {
    const r = filterCards(mixed, { source: 'robot', partition: DOUYIN, keyword: '' });
    expect(r.map((c) => c.id)).toEqual(['d2']);
  });

  test('没有 platform 字段的老卡片按 B站 处理', () => {
    const legacy = [{ id: 'old', source: 'local', partition: '知识', title: '老卡片', tags: [] }];
    expect(filterCards(legacy, { source: 'all', partition: DOUYIN, keyword: '' })).toHaveLength(0);
    expect(filterCards(legacy, { source: 'all', partition: '知识', keyword: '' })).toHaveLength(1);
  });
});
