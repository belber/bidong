// 收藏夹筛选：来源（local/robot/all）+ 标签（'全部' 或具体标签）可叠加。
function filterCards(cards, filters) {
  const source = filters && filters.source;
  const tag = filters && filters.tag;

  return cards.filter((card) => {
    if (source && source !== 'all' && card.source !== source) {
      return false;
    }
    if (tag && tag !== '全部' && !(card.tags || []).includes(tag)) {
      return false;
    }
    return true;
  });
}

module.exports = { filterCards };
