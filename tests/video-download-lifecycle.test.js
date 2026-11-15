const path=require('path');const {loadPage}=require('./helpers/page');
const mockApi={mediaOptions:jest.fn(),prepareVideo:jest.fn(),videoPreparation:jest.fn()};
jest.mock('../miniprogram/utils/api.js',()=>mockApi);
const flush=()=>new Promise(r=>setTimeout(r,0));
test.each(['queued','ready'])('leaving during POST does not restart polling or save in background: %s',async status=>{
 let resolve;mockApi.mediaOptions.mockResolvedValue([{qn:64,label:'720P'}]);
 mockApi.prepareVideo.mockImplementation(()=>new Promise(r=>resolve=r));
 mockApi.videoPreparation.mockClear();mockApi.videoPreparation.mockResolvedValue({status:'processing'});
 const {ctx}=loadPage(path.join(__dirname,'../miniprogram/pages/result/result.js'));
 ctx.data.cardId=1;ctx.data.media={clean:true};ctx._transcriptVisible=true;
 ctx.downloadPreparedVideo=jest.fn();ctx.onUnifiedVideoTap({currentTarget:{dataset:{kind:'video'}}});await flush();
 ctx.onHide();resolve({status,mode:'file',file_url:'/file'});await flush();
 ctx.onHide();
 expect(mockApi.videoPreparation).not.toHaveBeenCalled();expect(ctx.downloadPreparedVideo).not.toHaveBeenCalled();
 ctx.onHide();
});
