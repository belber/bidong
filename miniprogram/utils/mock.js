// 演示数据：后端尚未就绪时，用于在开发者工具里跑通界面流程。
// 后端 /api/parse 接入后删除此文件。
function buildMockVideo(link) {
  return {
    bvid: (link && link.bvid) || 'BV1BE4U6BEg8',
    title: '【小视频】092-宝藏男孩',
    up_name: '帅哥录屏',
    partition: '小视频',
    duration: 13,
    pubdate: Math.floor(new Date(2026, 7, 30, 0, 55).getTime() / 1000),
    tags: ['宝藏男孩', '帅哥', '宝藏'],
    desc: '一个关于宝藏男孩的小视频，轻松有趣，适合 #宝藏男孩 话题下观看。',
    subtitles: [
      { t: 5, text: '这里是第一条字幕金句' },
      { t: 9, text: '这里是第二条字幕金句' },
      { t: 12, text: '这里是第三条字幕金句' }
    ],
    source_url: (link && link.url) || 'https://www.bilibili.com/video/BV1BE4U6BEg8'
  };
}

// 收藏夹演示数据
const MOCK_CARDS = [
  {
    id: 'c1',
    bvid: 'BV1BE4U6BEg8',
    title: '【小视频】092-宝藏男孩',
    up_name: '帅哥录屏',
    partition: '小视频',
    duration: 13,
    cover_gradient: 'linear-gradient(135deg,#1b2440,#4a3f8f)',
    source: 'local',
    tags: ['宝藏男孩', '帅哥', '宝藏'],
    collected_at: Math.floor(new Date(2026, 7, 30, 0, 55).getTime() / 1000),
    month: '2026-08'
  },
  {
    id: 'c2',
    bvid: 'BV1xx411c7mD',
    title: '一口气看懂《三体》黑暗森林',
    up_name: '木鱼水心',
    partition: '影视',
    duration: 2712,
    cover_gradient: 'linear-gradient(135deg,#0b3d3a,#1f7a6d,#4ad2b5)',
    source: 'robot',
    tags: ['科幻', '深度'],
    collected_at: Math.floor(new Date(2026, 7, 28, 21, 10).getTime() / 1000),
    month: '2026-08'
  },
  {
    id: 'c3',
    bvid: 'BV1mQ4y1h7xK',
    title: '硬核讲透 Transformer',
    up_name: '3Blue1Brown',
    partition: '知识',
    duration: 1420,
    cover_gradient: 'linear-gradient(135deg,#3a1f5d,#c0502e)',
    source: 'robot',
    tags: ['AI', '长视频'],
    collected_at: Math.floor(new Date(2026, 6, 15, 9, 30).getTime() / 1000),
    month: '2026-07'
  }
];

module.exports = { buildMockVideo, MOCK_CARDS };
