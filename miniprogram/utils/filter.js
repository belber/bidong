// 收藏夹筛选：来源（local/robot/all）+ 分区（'全部' 或具体分区）+ 关键字，可叠加。
// 关键字匹配标题、UP主、分区、标签（大小写不敏感）。

function matchesKeyword(card, keyword) {
  if (!keyword) {
    return true;
  }
  const k = String(keyword).trim().toLowerCase();
  if (!k) {
    return true;
  }
  const fields = [
    card.title,
    card.up_name,
    card.partition,
    (card.tags || []).join(' ')
  ];
  return fields.some((f) => typeof f === 'string' && f.toLowerCase().indexOf(k) >= 0);
}

function filterCards(cards, filters) {
  const source = filters && filters.source;
  const partition = filters && filters.partition;
  const keyword = filters && filters.keyword;

  return cards.filter((card) => {
    if (source && source !== 'all' && card.source !== source) {
      return false;
    }
    if (partition && partition !== '全部' && card.partition !== partition) {
      return false;
    }
    if (!matchesKeyword(card, keyword)) {
      return false;
    }
    return true;
  });
}

module.exports = { filterCards };
