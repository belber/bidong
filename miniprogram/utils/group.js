// 收藏卡片按冗余 month 字段分组：月份倒序，组内按收藏时间倒序。
function groupByMonth(cards) {
  const byMonth = new Map();
  cards.forEach((card) => {
    if (!card.month) {
      return;
    }
    if (!byMonth.has(card.month)) {
      byMonth.set(card.month, []);
    }
    byMonth.get(card.month).push(card);
  });

  return Array.from(byMonth.keys())
    .sort((a, b) => (a < b ? 1 : -1))
    .map((month) => {
      const items = byMonth.get(month).slice().sort((a, b) => b.collected_at - a.collected_at);
      return { month, count: items.length, items };
    });
}

module.exports = { groupByMonth };
