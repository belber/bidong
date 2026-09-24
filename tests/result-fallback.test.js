const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const wxml = fs.readFileSync(path.join(root, 'miniprogram/pages/result/result.wxml'), 'utf8');
const appJson = JSON.parse(fs.readFileSync(path.join(root, 'miniprogram/app.json'), 'utf8'));

describe('fallback save guide', () => {
  const block = wxml.slice(wxml.indexOf('fallbackVisible'));

  test('用「换一种方式保存」代替失败提示，不出现负面词', () => {
    expect(block).toContain('换一种方式保存');
    expect(block).toContain('当前视频链接暂不支持在小程序内直接保存');
    expect(block).toContain('复制链接后，用手机浏览器打开即可保存视频');
    expect(block).not.toContain('自动下载失败');
    expect(block).not.toContain('下载失败');
    expect(block).not.toContain('错误');
    expect(block).not.toContain('异常');
  });

  test('提供 iOS / Android 双平台简洁步骤', () => {
    expect(block).toContain('iPhone');
    expect(block).toContain('Safari');
    expect(block).toContain('保存到「文件」');
    expect(block).toContain('Android');
    expect(block).toContain('Chrome');
    expect(block).toContain('点击下载');
  });

  test('底部提示时效并保留复制链接主按钮与关闭图标', () => {
    expect(block).toContain('链接可能有时效，请及时保存');
    expect(block).toContain('bindtap="onCopyFallback"');
    expect(block).toContain('class="fallback-close"');
  });

  test('不再依赖教程长图', () => {
    expect(block).not.toContain('fallback-guide.jpg');
  });

  test('复制链接而非转发小程序卡片', () => {
    expect(block).not.toContain('open-type="share"');
    expect(appJson.pages).not.toContain('pages/forward-video/forward-video');
  });
});

describe('download fallback behavior', () => {
  const js = fs.readFileSync(path.join(root, 'miniprogram/pages/result/result.js'), 'utf8');

  test('复制链接提示用户去浏览器下载，而不是发给文件传输助手', () => {
    const copyBlock = js.slice(js.indexOf('onCopyFallback'));
    expect(copyBlock).toContain('已复制，请用手机浏览器打开保存');
    expect(copyBlock).not.toContain('文件传输助手');
  });

  test('音频下载走后端中转，不再走 download-url 候选', () => {
    const audioBlock = js.slice(js.indexOf('exportRequest'));
    expect(audioBlock).toContain("return api.download(this.data.cardId, 'audio');");
    expect(js).not.toContain('startAudioExport');
  });

  test('音频下载成功直接用临时文件，不复制到本地用户目录', () => {
    const exportBlock = js.slice(js.indexOf('startExport(kind)'));
    expect(exportBlock).toContain("kind === 'audio'");
    expect(exportBlock).toContain('Promise.resolve(res.tempFilePath)');
  });

  test('视频下载使用并发候选，任一成功即返回', () => {
    expect(js).toContain('downloadMediaParallel(candidates');
  });
});
