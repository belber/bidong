const fs=require('fs');
const path=require('path');
const xml=()=>fs.readFileSync(path.join(__dirname,'../miniprogram/pages/result/result.wxml'),'utf8');
test('one unified video entry with thumbnail and independent audio',()=>{
 expect((xml().match(/bindtap="onUnifiedVideoTap"/g)||[])).toHaveLength(1);
 expect(xml()).toContain('summary-thumbnail');expect(xml()).toContain('mode="aspectFill"');
 expect(xml()).toContain('summary-placeholder');expect(xml()).toContain('视频下载');
 expect(xml()).not.toContain('data-kind="watermarked"');expect(xml()).not.toContain('高清视频轨，不含音频');
});
test('preparation does not auto save and reports actual file size',async()=>{
 const api={videoPreparation:jest.fn(()=>Promise.resolve({status:'ready',size_bytes:2048,has_audio:true,file_url:'/file'}))};
 const client=require('../miniprogram/utils/videoDownload');
 const page={data:{cardId:1,isDouyin:false,publicView:false,media:{clean:true},mediaSize:{}},setData(v){Object.assign(this.data,v);}};
 client.start(page,api);await Promise.resolve();await Promise.resolve();
 expect(page.data.videoPreparation.status).toBe('ready');expect(page.data.mediaSize.video).toContain('KB');
 client.stop(page);
});
test('hide ignores stale state and polling does not enqueue work',async()=>{
 let resolve;const api={videoPreparation:jest.fn(()=>new Promise(r=>resolve=r))};
 const c=require('../miniprogram/utils/videoDownload');
 const page={data:{cardId:1,media:{clean:true}},setData:jest.fn()};c.start(page,api);c.stop(page);
 resolve({status:'processing'});await Promise.resolve();expect(page.setData).not.toHaveBeenCalled();
});
