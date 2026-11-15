const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const js=fs.readFileSync('miniprogram/pages/result/result.js','utf8');
test('转发先检查文件且失效后恢复下载入口',()=>{const s=js.slice(js.indexOf('  shareExport(kind) {'),js.indexOf('  computeDownloadSpeed'));assert(s.includes('accessSync'));assert(s.includes('failExport'));});
test('下载完成优先具名文件且回填实际大小',()=>{const s=js.slice(js.indexOf('  startExport(kind) {'),js.indexOf('  openExportFallback'));assert(s.includes('copyToNamed(res.tempFilePath, filename).catch'));assert(s.includes('mediaSize'));assert(s.includes('info.size'));});
test('文件不存在时不唤起分享并改成失败状态',async()=>{
 let shares=0,failed=false,toast='';
 const body=js.slice(js.indexOf('  shareExport(kind) {'),js.indexOf('  computeDownloadSpeed')).trim().replace(/,$/,'');
 const obj=vm.runInNewContext('({'+body+'})',{wx:{getFileSystemManager:()=>({accessSync:()=>{throw new Error('missing');}})},shareFilePromise:()=>{shares++;return Promise.resolve();},failExport:()=>{failed=true;return {};},toast:s=>toast=s});
 obj.data={exports:{audio:{path:'/missing'}}};obj.exportName=()=> 'audio.m4a';obj.setData=()=>{};obj.shareExport('audio');await new Promise(r=>setImmediate(r));assert.equal(shares,0);assert(failed);assert(toast.includes('重新下载'));
});

test('点击处理栈内立即调用分享',()=>{
 let shares=0;
 const body=js.slice(js.indexOf('  shareExport(kind) {'),js.indexOf('  computeDownloadSpeed')).trim().replace(/,$/,'');
 const obj=vm.runInNewContext('({'+body+'})',{wx:{getFileSystemManager:()=>({accessSync(){}})},shareFilePromise:()=>{shares++;return new Promise(()=>{});}});
 obj.data={exports:{audio:{path:'/exists'}}};obj.exportName=()=> 'a.m4a';obj.shareExport('audio');assert.equal(shares,1);
});
test('音频分享成功不显示额外提示',async()=>{
 const messages=[];
 const body=js.slice(js.indexOf('  shareExport(kind) {'),js.indexOf('  computeDownloadSpeed')).trim().replace(/,$/,'');
 const obj=vm.runInNewContext('({'+body+'})',{wx:{getFileSystemManager:()=>({accessSync(){}})},shareFilePromise:()=>Promise.resolve(),markExportSaved:x=>x,toast:s=>messages.push(s)});
 obj.data={exports:{audio:{path:'/exists'}}};obj.exportName=()=> 'a.m4a';obj.setData=()=>{};obj.reportDownload=()=>{};
 obj.shareExport('audio');await new Promise(r=>setImmediate(r));assert.deepEqual(messages,[]);
});
