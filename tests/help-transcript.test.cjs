const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
test('更多信息操作文字为红色',()=>assert.match(fs.readFileSync('miniprogram/pages/result/result.wxss','utf8'),/\.more-arrow\s*\{[^}]*color:\s*#E53935/i));
test('帮助覆盖文案入口、导出与异常说明',()=>{const s=fs.readFileSync('miniprogram/pages/help/help.wxml','utf8');for(const text of ['提取文案','时间轴','纯文本','转发到微信','无语音','重试','原字幕'])assert(s.includes(text),text);});
