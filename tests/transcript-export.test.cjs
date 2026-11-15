const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('miniprogram/pages/transcript/transcript.js','utf8');
test('TXT先下载，再点击转发；取消后复用已下载文件',async()=>{
 let page,downloads=0,shares=0;
 const wx={env:{USER_DATA_PATH:'/local'},showToast(){},downloadFile(o){downloads++;o.success({statusCode:200,tempFilePath:'/tmp/txt'});return {abort(){}};},getFileSystemManager(){return {copyFile(o){o.success();}};},shareFileMessage(o){shares++;o.fail({errMsg:'cancel'});}};
 vm.runInNewContext(source,{wx,Page:p=>page=p,require:p=>p.endsWith('/api')?{transcriptExport:async()=>({url:'https://test/txt',header:{}})}:p.endsWith('/format')?{formatDuration:()=>''}:{decorate:()=>({})}});
 page.data.cardId=1;page.data.transcript={status:'completed'};page.setData=p=>Object.assign(page.data,p);
 page.onExportTxt();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(downloads,1);assert.equal(shares,0);assert.equal(page.data.exportState,'ready');
 page.onExportTxt();page.onExportTxt();assert.equal(shares,2);assert.equal(downloads,1);
});
test('完成后按钮明确标注转发到微信',()=>assert(fs.readFileSync('miniprogram/pages/transcript/transcript.wxml','utf8').includes("exportState === 'ready' ? '转发到微信'")));
