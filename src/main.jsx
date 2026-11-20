import React,{useEffect,useMemo,useRef,useState} from 'react';
import{createRoot}from'react-dom/client';
import{Play,Pause,Volume2,VolumeX,Maximize,Minimize,Cloud,Home,Folder,Image,DatabaseBackup,Clock3,Star,Users,RefreshCw,Trash2,Settings,Search,Plus,Upload,FolderPlus,Grid2X2,List,ChevronRight,HardDrive,WifiOff,FileText,FileArchive,File,Video,Download,MoreHorizontal,Code,X,ArrowLeft,Pencil,MoveRight,Eye,RotateCcw,Check,ChevronDown,CircleAlert}from'lucide-react';
import{all,save,read,erase}from'./storage';
import './style.css';
const uid=()=>crypto.randomUUID();
const size=n=>n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';
const date=n=>new Date(n).toLocaleDateString('pt-BR');
function IconFile({item,large=false}){const n=large?56:26;if(item.kind==='folder')return <Folder size={n} fill="#8db8fc" color="#a8cbff" strokeWidth={1.4}/>;if(item.type?.startsWith('image/'))return <Image size={n} color="#c3a4ff"/>;if(item.type?.startsWith('video/'))return <Video size={n} color="#70caa8"/>;if(/zip|tar|gz|rar/i.test(item.name))return <FileArchive size={n} color="#e5bd78"/>;if(item.name.toLowerCase().endsWith('.pdf'))return <FileText size={n} color="#fa929e"/>;return <File size={n} color="#b8b8ce"/>}
function TelegramSettings({onToast}){
const [status,setStatus]=useState(null),[phone,setPhone]=useState(''),[code,setCode]=useState(''),[password,setPassword]=useState(''),[step,setStep]=useState('qr-choice'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[qrImage,setQrImage]=useState('');
const [storage,setStorage]=useState(null),[storageBusy,setStorageBusy]=useState(false),[storageError,setStorageError]=useState('');
const endpoint='http://127.0.0.1:8000';
async function call(path,data){const response=await fetch(endpoint+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},...(data!==undefined?{body:JSON.stringify(data)}:{})});const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'Falha na conexão');return result}
async function refresh(){try{const r=await call('/api/telegram/status');setStatus(r);setStep(r.connected?'connected':'qr-choice')}catch{setStatus({offline:true,connected:false})}}
useEffect(()=>{refresh()},[]);
useEffect(()=>{if(step!=='connected'||!status?.connected)return;let cancelled=false;
(async()=>{setStorageBusy(true);setStorageError('');try{
  const result=await call('/api/telegram/storage/ensure',{});
  if(!cancelled)setStorage(result);
}catch(e){if(!cancelled)setStorageError(e.message)}
finally{if(!cancelled)setStorageBusy(false)}
})();
return()=>{cancelled=true};
},[step,status?.connected,status?.id]);
useEffect(()=>{if(step!=='qr')return;let stopped=false;const timer=setInterval(async()=>{try{const r=await call('/api/telegram/qr/status');if(stopped)return;if(r.step==='connected'){setStatus({...r,configured:true});setStep('connected')}else if(r.step==='password')setStep('qr-password');else if(r.step==='expired'||r.step==='error'){setStep('qr-expired');if(r.detail)setError(r.detail)}}catch(e){if(!stopped)setError(e.message)}},1400);return()=>{stopped=true;clearInterval(timer)}},[step]);
async function perform(path,data){setBusy(true);setError('');try{const r=await call('/api/telegram/'+path,data);if(r.image){setQrImage(r.image);setStep('qr')}else if(r.step)setStep(r.step);if(r.connected){setStatus({...r,configured:true});setPassword('');setCode('');onToast?.({kind:'success',message:'Telegram conectado com sucesso'})}else if(path==='logout'||path==='disconnect'){setStorage(null);setStorageError('');setQrImage('');await refresh();onToast?.({kind:'info',message:path==='logout'?'Sessão do Telegram encerrada':'Conexão encerrada'})}}catch(e){setError(e.message);onToast?.({kind:'error',message:e.message,duration:6500})}finally{setBusy(false)}}
return <section className="telegram-panel"><div className="telegram-header"><div className="tg-header-icon"><img src="/drive-cloud-logo.svg" alt=""/></div><div><h2>{step==='connected'?'Conta conectada':'Conectar Telegram'}</h2><p>{step==='connected'?'Sua conta autoriza o armazenamento privado do Drive Cloud.':'Autorize a conta pelo QR Code do Telegram.'}</p></div><span className={status?.connected?'tg-connection-tag active':'tg-connection-tag'}>{status?.connected?'Conectado':'Desconectado'}</span></div>
{status?.offline?<div className="tg-warning">Backend local desligado. Inicie o servidor Python na porta 8000 e atualize esta página.</div>:status&&!status.configured?<div className="tg-warning">Configure TELEGRAM_API_ID e TELEGRAM_API_HASH no arquivo backend/.env e reinicie o backend.</div>:step==='connected'?<div className="tg-connected-card">
<div className="tg-account-line"><div className="tg-account-avatar">{(status?.name||'T').slice(0,1).toUpperCase()}{status?.connected&&<img src={'http://127.0.0.1:8000/api/telegram/avatar?account='+encodeURIComponent(status.id||'')} alt="" onError={event=>{event.currentTarget.style.display='none'}}/>}</div><div><strong>{status?.name||'Telegram'}</strong><small>{status?.username?'@'+status.username:'Perfil conectado ao Drive Cloud'}</small></div><span className="tg-account-online"><Check size={15}/> Ativa</span></div>
<div className="tg-channel-line"><div className="tg-channel-icon"><Folder size={20}/></div><div><strong>{storageBusy?'Verificando canal privado...':storage?.ready?storage.title:'Canal privado não configurado'}</strong><small>{storage?.ready?'Canal privado conectado e verificado.':storageError||'Configure um canal para armazenar seus arquivos.'}</small></div>{storage?.ready&&<span className="tg-channel-ok"><Check size={17}/></span>}</div>
{!storage?.ready&&!storageBusy&&<button className="tg-setup-button" disabled={storageBusy} onClick={async()=>{setStorageBusy(true);setStorageError('');try{setStorage(await call('/api/telegram/storage/ensure',{}))}catch(e){setStorageError(e.message)}finally{setStorageBusy(false)}}}>Preparar canal de armazenamento</button>}
<div className="tg-connected-actions"><button disabled={busy} onClick={()=>perform('disconnect',{})}>Desconectar backend</button><button disabled={busy} onClick={()=>{if(confirm('Revogar a sessão do Telegram neste computador?'))perform('logout',{})}}>Sair do Telegram</button></div></div>:<div className="tg-form">
{step==='qr-choice'?<><p className="tg-note">No celular: Telegram → Configurações → Dispositivos → Conectar dispositivo.</p><button disabled={busy||!status?.configured} onClick={()=>perform('qr/start',{})}>Gerar QR Code</button><button className="tg-back" onClick={()=>setStep('phone')}>Entrar com telefone</button></>:null}
{step==='qr'?<><div className="tg-qr"><img src={qrImage} alt="QR Code temporário para conectar sua conta do Telegram"/></div><p className="tg-note">Abra o Telegram no celular, entre em Dispositivos e escaneie o código. Aguardando autorização...</p><button className="tg-back" onClick={()=>perform('qr/start',{})}>Gerar novo QR Code</button><button className="tg-back" onClick={()=>setStep('phone')}>Usar telefone</button></>:null}
{step==='qr-expired'?<><div className="tg-warning">O QR Code expirou ou não pôde ser validado.</div><button disabled={busy} onClick={()=>perform('qr/start',{})}>Gerar outro QR Code</button><button className="tg-back" onClick={()=>setStep('phone')}>Usar telefone</button></>:null}
{step==='qr-password'?<><label>Senha de duas etapas do Telegram</label><input type="password" autoComplete="off" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Senha 2FA"/><button disabled={busy} onClick={()=>perform('qr/password',{password})}>Confirmar senha</button></>:null}
{step==='phone'?<><label>Telefone com DDI</label><input autoComplete="tel" placeholder="+5511999999999" value={phone} onChange={e=>setPhone(e.target.value)}/><button disabled={busy||!status?.configured} onClick={()=>perform('send-code',{phone})}>Enviar código de verificação</button><button className="tg-back" onClick={()=>setStep('qr-choice')}>Usar QR Code</button></>:null}
{step==='code'?<><label>Código recebido no Telegram</label><input autoComplete="one-time-code" inputMode="numeric" placeholder="Código de login" value={code} onChange={e=>setCode(e.target.value)}/><button disabled={busy} onClick={()=>perform('verify-code',{code})}>Confirmar código</button><button className="tg-back" onClick={()=>setStep('phone')}>Voltar</button></>:null}
{step==='password'?<><label>Senha de verificação em duas etapas</label><input type="password" autoComplete="off" placeholder="Sua senha 2FA" value={password} onChange={e=>setPassword(e.target.value)}/><button disabled={busy} onClick={()=>perform('verify-password',{password})}>Autorizar</button></>:null}
</div>}
<p className="tg-security-note"><CircleAlert size={15}/> A sessão fica neste computador. Não compartilhe o QR Code, códigos, senha 2FA ou os arquivos de sessão.</p></section>
}

const isCloudImage=item=>item.kind==='file'&&(item.mime?.startsWith('image/')||/\.(jxl|jpe?g|png|gif|webp|bmp|tiff?)$/i.test(item.name));
const isCloudVideo=item=>item.kind==='file'&&/\.(mp4|webm|m4v)$/i.test(item.name);
// Reuse successful previews across navigation, list/grade switches and remounts.
const cloudPreviewCache=new Map();
function cachedCloudPreview(item){
 const key=item.id+':'+(item.message_id??'');
 const existing=cloudPreviewCache.get(key);
 if(existing){if(existing.url)return Promise.resolve(existing.url);if(existing.promise)return existing.promise;if(existing.retryAt>Date.now())return Promise.reject(Error('A prévia está temporariamente indisponível'))}
 const controller=new AbortController();
 const timeout=setTimeout(()=>controller.abort(),18000);
 const promise=fetch('http://127.0.0.1:8000/api/cloud/preview/'+encodeURIComponent(item.id),{signal:controller.signal,cache:'force-cache'}).then(response=>{
   if(!response.ok)throw Error('Prévia indisponível');
   return response.blob();
 }).then(blob=>{
   const url=URL.createObjectURL(blob);
   cloudPreviewCache.delete(key);cloudPreviewCache.set(key,{url});
   // Bound thumbnail memory usage and revoke older blob URLs.
   while(cloudPreviewCache.size>100){
     const firstKey=cloudPreviewCache.keys().next().value;
     const value=cloudPreviewCache.get(firstKey);
     if(value?.url)URL.revokeObjectURL(value.url);
     cloudPreviewCache.delete(firstKey);
   }
   return url;
 }).catch(error=>{
   cloudPreviewCache.set(key,{retryAt:Date.now()+30000});
   throw error;
 }).finally(()=>clearTimeout(timeout));
 cloudPreviewCache.set(key,{promise});
 return promise;
}
function CloudThumbnail({item,compact=false}){
 const [result,setResult]=useState({url:cloudPreviewCache.get(item.id+':'+(item.message_id??''))?.url||null,failed:false});
 useEffect(()=>{
   if(item.kind==='folder'||!isCloudImage(item))return;
   let live=true;
   const key=item.id+':'+(item.message_id??'');
   const cached=cloudPreviewCache.get(key)?.url;
   if(cached){setResult({url:cached,failed:false});return}
   setResult({url:null,failed:false});
   cachedCloudPreview(item).then(url=>{if(live)setResult({url,failed:false})}).catch(()=>{if(live)setResult({url:null,failed:true})});
   return()=>{live=false};
 },[item.id,item.message_id,item.kind,item.name]);
 if(item.kind==='folder')return <div className="cloud-thumb-folder"><Folder size={compact?25:78} fill="#96bcf1" color="#b1d0ff" strokeWidth={1.2}/></div>;
 if(isCloudVideo(item))return <div className="cloud-thumb-video" aria-label="Vídeo"><Play size={compact?16:32} fill="currentColor"/></div>;
 if(!isCloudImage(item))return <div className="cloud-thumb-fallback"><IconFile item={item} large={!compact}/></div>;
 if(result.failed)return <div className="cloud-thumb-fallback cloud-thumb-retry"><IconFile item={item} large={!compact}/><button className="cloud-preview-retry" title="Tentar carregar miniatura novamente" aria-label={'Recarregar miniatura de '+item.name} onClick={event=>{event.stopPropagation();cloudPreviewCache.delete(item.id+':'+(item.message_id??''));setResult({url:null,failed:false});cachedCloudPreview(item).then(url=>setResult({url,failed:false})).catch(()=>setResult({url:null,failed:true}))}}><RefreshCw size={compact?12:16}/></button></div>;
 return <div className="cloud-thumb-photo">{!result.url&&<div className="dc-thumb-placeholder" role="status" aria-label="Preparando miniatura"><DriveCloudLoader size={30} label="Preparando miniatura"/></div>}{result.url&&<img src={result.url} alt={item.name}/>}</div>
}
function DriveToast({toast,progress,onDismiss}){const [closing,setClosing]=useState(false);
useEffect(()=>setClosing(false),[toast?.id]);
useEffect(()=>{if(!toast)return;const t=setTimeout(()=>setClosing(true),toast.duration||4200);return()=>clearTimeout(t)},[toast?.id]);
useEffect(()=>{if(!closing)return;const t=setTimeout(onDismiss,260);return()=>clearTimeout(t)},[closing]);
if(progress){const percentage=Math.round(progress.completed/Math.max(1,progress.total)*100);return <div className="dc-toast dc-toast-progress" role="status" aria-live="polite"><span className="dc-toast-symbol deleting"><Trash2 size={19}/></span><div className="dc-toast-progress-body"><div className="dc-toast-progress-title"><strong>{progress.kind==='permanent'?'Excluindo arquivos...':'Movendo para a lixeira...'}</strong><span>{percentage}%</span></div><p>{progress.completed} de {progress.total} item(ns) • {progress.current||'Preparando...'}</p><div className="dc-toast-progress-track"><span style={{width:percentage+'%'}}/></div></div><button className="dc-toast-progress-cancel" onClick={progress.cancel} disabled={progress.state==='cancelling'}>{progress.state==='cancelling'?'Parando':'Cancelar'}</button></div>}
if(!toast)return null;
const Icon=toast.kind==='error'?X:toast.kind==='info'?Cloud:Check;
return <div className={'dc-toast '+(closing?'dc-toast-out':'')} role="status" aria-live="polite"><span className={'dc-toast-symbol '+toast.kind}><Icon size={18}/></span><div className="dc-toast-message">{toast.message}</div>{toast.undo&&<button className="dc-toast-undo" onClick={()=>{toast.undo();setClosing(true)}}>Desfazer</button>}<button className="dc-toast-close" title="Fechar notificação" aria-label="Fechar notificação" onClick={()=>setClosing(true)}><X size={17}/></button></div>}
function DriveVideoPlayer({src,name,onError}){
 const videoRef=useRef(null),shellRef=useRef(null),seekBarRef=useRef(null),hideControlsTimer=useRef(null),tapRef=useRef(null),skipRef=useRef(null),feedbackTimer=useRef(null),skipTimer=useRef(null);
 const [playing,setPlaying]=useState(false),[waiting,setWaiting]=useState(true),[controlsVisible,setControlsVisible]=useState(true);
 const [current,setCurrent]=useState(0),[duration,setDuration]=useState(0);
 const [volume,setVolume]=useState(1),[muted,setMuted]=useState(false),[volumeOpen,setVolumeOpen]=useState(false);
 const [full,setFull]=useState(false),[canPip,setCanPip]=useState(false),[pip,setPip]=useState(false),[quality,setQuality]=useState('');
 const [skipIndicator,setSkipIndicator]=useState(null),[centerFeedback,setCenterFeedback]=useState(null);
 const stamp=n=>Number.isFinite(n)?Math.floor(n/3600)>0?[Math.floor(n/3600),Math.floor(n%3600/60),Math.floor(n%60)].map(x=>String(x).padStart(2,'0')).join(':'):[Math.floor(n/60),Math.floor(n%60)].map(x=>String(x).padStart(2,'0')).join(':'):'0:00';
 const clearTap=()=>{if(tapRef.current?.timer)clearTimeout(tapRef.current.timer);tapRef.current=null};
 const syncSeekBar=()=>{
  const v=videoRef.current, bar=seekBarRef.current;
  if(!v||!bar||!Number.isFinite(v.duration)||v.duration<=0)return;
  const progress=Math.max(0,Math.min(100,v.currentTime/v.duration*100));
  bar.value=String(v.currentTime);
  bar.style.setProperty('--progress',progress+'%');
 };
 const scheduleControlsHide=()=>{
  clearTimeout(hideControlsTimer.current);
  if(videoRef.current&&!videoRef.current.paused&&!videoRef.current.seeking&&!waiting&&!volumeOpen){
   hideControlsTimer.current=setTimeout(()=>{
    if(!document.activeElement?.matches?.(':focus-visible'))setControlsVisible(false)
   },2600);
  }
 };
 const revealControls=()=>{setControlsVisible(true);scheduleControlsHide()};
 useEffect(()=>{
  let raf=0;
  if(playing){const tick=()=>{syncSeekBar();raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick)}
  else syncSeekBar();
  return()=>cancelAnimationFrame(raf);
 },[playing,duration]);
 useEffect(()=>{revealControls();return()=>clearTimeout(hideControlsTimer.current)},[playing,waiting,volumeOpen]);
 const flashCenter=kind=>{clearTimeout(feedbackTimer.current);setCenterFeedback(kind);feedbackTimer.current=setTimeout(()=>setCenterFeedback(null),620)};
 const toggle=()=>{const v=videoRef.current;if(!v)return;if(v.paused){v.play().then(()=>flashCenter('play')).catch(()=>{})}else{v.pause();flashCenter('pause')}};
 const seek=value=>{const v=videoRef.current;if(v&&Number.isFinite(v.duration)&&v.duration>0){v.currentTime=Math.max(0,Math.min(v.duration,Number(value)));setCurrent(v.currentTime);syncSeekBar();revealControls()}};
 const skip=side=>{
  const v=videoRef.current;
  if(!v||!Number.isFinite(v.duration)||v.duration<=0)return;
  const now=Date.now(),last=skipRef.current;
  const cumulative=last?.side===side&&now-last.at<1350?last.amount+10:10;
  skipRef.current={side,amount:cumulative,at:now};
  seek(v.currentTime+(side==='right'?10:-10));
  setSkipIndicator({side,amount:cumulative});
  clearTimeout(skipTimer.current);
  skipTimer.current=setTimeout(()=>setSkipIndicator(null),850);
 };
 const handleGesture=e=>{
  if(e.pointerType==='mouse'&&e.button!==0)return;
  const rect=e.currentTarget.getBoundingClientRect();
  const fraction=(e.clientX-rect.left)/rect.width;
  if(fraction>=.39&&fraction<=.61){clearTap();toggle();return}
  const side=fraction<.5?'left':'right',now=Date.now();
  const previous=tapRef.current;
  if(previous&&previous.side===side&&now-previous.at<350){
   clearTap();
   skip(side);
   return;
  }
  clearTap();
  tapRef.current={side,at:now,timer:setTimeout(()=>{tapRef.current=null;toggle()},350)};
 };
 const fullscreen=async()=>{const el=shellRef.current;if(!el)return;try{if(document.fullscreenElement)await document.exitFullscreen();else if(el.requestFullscreen)await el.requestFullscreen()}catch{}};
 const togglePip=async()=>{const v=videoRef.current;if(!v||!v.requestPictureInPicture)return;try{if(document.pictureInPictureElement)await document.exitPictureInPicture();else await v.requestPictureInPicture()}catch{}};
 const onMetadata=e=>{const v=e.currentTarget;setDuration(v.duration);setWaiting(false);setQuality(v.videoHeight>=720?'HD':'')};
 useEffect(()=>{
  const listener=()=>setFull(!!document.fullscreenElement);
  document.addEventListener('fullscreenchange',listener);
  setCanPip(Boolean(document.pictureInPictureEnabled&&videoRef.current?.requestPictureInPicture));
  const v=videoRef.current;
  const onEnter=()=>setPip(true),onLeave=()=>setPip(false);
  v?.addEventListener('enterpictureinpicture',onEnter);
  v?.addEventListener('leavepictureinpicture',onLeave);
  return()=>{document.removeEventListener('fullscreenchange',listener);v?.removeEventListener('enterpictureinpicture',onEnter);v?.removeEventListener('leavepictureinpicture',onLeave);clearTap();clearTimeout(skipTimer.current);clearTimeout(feedbackTimer.current);clearTimeout(hideControlsTimer.current)};
 },[]);
 return <div ref={shellRef} className={'dc-video-player dc-video-player-youtube '+(controlsVisible?'controls-visible':'controls-hidden')} tabIndex={0} aria-label={'Player de vídeo: '+name} onPointerMove={revealControls} onPointerDown={revealControls} onFocusCapture={revealControls} onKeyDown={e=>{revealControls();
  if(e.target.tagName==='INPUT'||e.target.tagName==='BUTTON')return;
  if(e.key===' '||e.key==='k'){e.preventDefault();toggle()}
  else if(e.key==='ArrowRight'){e.preventDefault();skip('right')}
  else if(e.key==='ArrowLeft'){e.preventDefault();skip('left')}
  else if(e.key==='f'){e.preventDefault();fullscreen()}
  else if(e.key==='m'){e.preventDefault();const v=videoRef.current;if(v){v.muted=!v.muted;setMuted(v.muted)}}
 }}>
  <video ref={videoRef} src={src} playsInline preload="metadata" onLoadStart={()=>setWaiting(true)} onWaiting={()=>setWaiting(true)} onCanPlay={()=>setWaiting(false)} onPlaying={()=>{setPlaying(true);setWaiting(false)}} onPause={()=>setPlaying(false)} onTimeUpdate={e=>{setCurrent(e.currentTarget.currentTime);syncSeekBar()}} onSeeked={()=>{syncSeekBar();revealControls()}} onLoadedMetadata={onMetadata} onDurationChange={e=>setDuration(e.currentTarget.duration)} onError={onError}/>
  <div className="dc-video-gesture-layer" aria-label="Toque duas vezes à esquerda para voltar 10 segundos ou à direita para avançar" onPointerUp={handleGesture} onDoubleClick={e=>e.preventDefault()}/>
  {waiting&&<div className="dc-video-buffer" aria-label="Carregando vídeo"><span className="dc-video-spinner"/></div>}
  {!playing&&!waiting&&<button type="button" className="dc-video-big-play" aria-label="Reproduzir vídeo" onClick={toggle}><Play size={28} fill="currentColor"/></button>}
  {centerFeedback&&playing&&<div className="dc-video-center-feedback" aria-hidden="true">{centerFeedback==='pause'?<Pause size={29} fill="currentColor"/>:<Play size={29} fill="currentColor"/>}</div>}
  {skipIndicator&&<div key={skipIndicator.side+'-'+skipIndicator.amount} className={'dc-video-skip-feedback '+(skipIndicator.side==='left'?'dc-video-skip-left':'dc-video-skip-right')} aria-live="polite"><span>{skipIndicator.side==='left'?'−':'+'}{skipIndicator.amount}s</span></div>}
  <div className="dc-video-controls" onPointerDown={()=>{clearTimeout(hideControlsTimer.current);setControlsVisible(true)}} onPointerUp={scheduleControlsHide}>
   <div className="dc-video-above-progress"><span className="dc-video-timestamp">{stamp(current)} / {stamp(duration)}</span><button type="button" aria-label={full?'Sair da tela cheia':'Tela cheia'} onClick={fullscreen}>{full?<Minimize size={20}/>:<Maximize size={20}/>}</button></div>
   <input ref={seekBarRef} className="dc-video-seek" aria-label="Progresso do vídeo" type="range" min="0" max={duration||1} step=".05" defaultValue={0} onChange={e=>seek(e.target.value)} />
   <div className="dc-video-control-row">
    <button type="button" aria-label={playing?'Pausar':'Reproduzir'} onClick={toggle}>{playing?<Pause size={20} fill="currentColor"/>:<Play size={20} fill="currentColor"/>}</button>
    {quality&&<span className="dc-video-quality" title="Qualidade original do arquivo; troca de resolução não disponível">{quality}</span>}
    {canPip&&<button type="button" aria-label={pip?'Fechar player flutuante':'Abrir player flutuante'} title="Picture-in-Picture" onClick={togglePip}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><rect x="12" y="12" width="8" height="6" rx="1" fill="currentColor" stroke="none"/></svg></button>}
    <span className="dc-video-flex"/>
    <div className={'dc-video-volume-wrap '+(volumeOpen?'is-open':'')}>
     <input aria-label="Volume" className="dc-video-volume" type="range" min="0" max="1" step=".05" value={muted?0:volume} onChange={e=>{const n=Number(e.target.value);setVolume(n);setMuted(n===0);if(videoRef.current){videoRef.current.volume=n;videoRef.current.muted=n===0}}}/>
     <button type="button" aria-label={muted||volume===0?'Ativar áudio':'Configurar volume'} aria-expanded={volumeOpen} title="Áudio e volume" onClick={()=>setVolumeOpen(open=>!open)}>{muted||volume===0?<VolumeX size={21}/>:<Volume2 size={21}/>}</button>
    </div>
   </div>
  </div>
 </div>
}
function SharedMediaDisplay({src,statusUrl,name,video=false}){
 const [failure,setFailure]=useState(''),[attempt,setAttempt]=useState(0);
 async function fail(){
  try{
   const response=await fetch(statusUrl,{cache:'no-store'});
   if(!response.ok){const body=await response.json().catch(()=>({}));setFailure(body.detail||'Mídia indisponível (HTTP '+response.status+').')}
   else setFailure('Não foi possível exibir esta mídia no navegador. Verifique se o formato é compatível.')
  }catch{setFailure('Não foi possível conectar ao backend local. Verifique se ele está ativo.')}
 }
 return <div className="dc-shared-media-view">
  {failure?<div className="dc-shared-media-error"><CircleAlert size={24}/><strong>Prévia indisponível</strong><p>{failure}</p><button type="button" onClick={()=>{setFailure('');setAttempt(x=>x+1)}}><RefreshCw size={15}/> Tentar novamente</button></div>
  :video?<DriveVideoPlayer key={attempt} src={src} name={name} onError={fail}/>
  :<img key={attempt} src={src} alt={name} onError={fail}/>}
 </div>
}
function SharedMediaThumb({src,video=false}){
 const [failed,setFailed]=useState(false);
 if(failed)return video?<Play size={24}/>:<Image size={24}/>;
 return video?<span className="dc-video-thumbnail"><Play size={22} fill="currentColor"/></span>:<img className="public-media-thumbnail" loading="lazy" alt="" src={src} onError={()=>setFailed(true)}/>;
}
function EmbeddedMedia({token}){
 const [data,setData]=useState(null),[error,setError]=useState('');
 const endpoint='http://127.0.0.1:8000/api/public/share/'+encodeURIComponent(token);
 useEffect(()=>{let cancelled=false;fetch(endpoint,{cache:'no-store'}).then(async r=>{const body=await r.json();if(!r.ok)throw Error(body.detail||'Mídia indisponível');return body}).then(d=>{if(!cancelled)setData(d)}).catch(e=>{if(!cancelled)setError(e.message)});return()=>{cancelled=true}},[token]);
 const video=data&&/\.(mp4|webm|m4v)$/i.test(data.name);
 const picture=data&&/\.(png|jpe?g|webp|gif|jxl|bmp|tiff?)$/i.test(data.name);
 return <div className="dc-embedded-media">{error?<div className="dc-embed-fail">{error}</div>:!data?<DriveCloudLoader size={64} label="Carregando mídia"/>:data.mode!=='embed'?<div className="dc-embed-fail">Incorporação não autorizada.</div>:data.kind!=='file'||(!video&&!picture)?<div className="dc-embed-fail">Formato não suportado.</div>:<SharedMediaDisplay src={endpoint+'/media?access='+encodeURIComponent(data.media_ticket||'')} statusUrl={endpoint+'/media-status'} name={data.name} video={video}/>}</div>
}
function PublicShareView({token}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[current,setCurrent]=useState(null),[opened,setOpened]=useState(null),[search,setSearch]=useState(''),[view,setView]=useState('list');
 const endpoint='http://127.0.0.1:8000/api/public/share/'+encodeURIComponent(token);
 useEffect(()=>{let active=true;fetch(endpoint,{cache:'no-store'}).then(async r=>{const x=await r.json();if(!r.ok)throw Error(x.detail||'Link indisponível');return x}).then(x=>{if(active){setData(x);setCurrent(x.root_id||null)}}).catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[token]);
 const list=data?.items||[];
 const folders=new Map(list.filter(x=>x.kind==='folder').map(x=>[x.id,x]));
 const root=data?.root_id;
 const currentFolder=current===root?null:folders.get(current);
 const parents=[];let walk=current;const seen=new Set();
 while(walk&&walk!==root&&!seen.has(walk)){seen.add(walk);const folder=folders.get(walk);if(!folder)break;parents.unshift(folder);walk=folder.parent}
 const name=currentFolder?.name||data?.name||'Pasta compartilhada';
 const visible=list.filter(x=>x.parent===current).filter(x=>!search.trim()||x.name.toLocaleLowerCase('pt-BR').includes(search.trim().toLocaleLowerCase('pt-BR'))).sort((a,b)=>a.kind===b.kind?a.name.localeCompare(b.name,'pt-BR'):a.kind==='folder'?-1:1);
 function goFolder(id){setCurrent(id);setSearch('');setOpened(null)}
 const up=currentFolder?.parent||root;
 const image=item=>/\.(jpe?g|png|gif|webp|jxl|bmp|tiff?)$/i.test(item.name);
 const video=item=>/\.(mp4|webm|m4v)$/i.test(item.name);
 const mediaUrl=item=>endpoint+'/media/'+encodeURIComponent(item.id)+'?access='+encodeURIComponent(data?.media_ticket||'');
 return <main className="public-share-screen">
 <header className="public-share-header"><span className="public-share-brand"><img src="/drive-cloud-logo.svg" alt=""/><b>Drive Cloud</b></span><span className="public-share-header-pill"><Check size={13}/> Link de acesso</span></header>
 <div className="public-drive-wrap">
 {loading?<div className="public-share-loading" aria-busy="true"><div className="dc-shimmer public-loading-hero"/><div className="dc-shimmer public-loading-nav"/><div className="public-loading-items">{[0,1,2,3].map(i=><div className="dc-shimmer" key={i}/>)}</div><p><DriveCloudLoader size={48} label="Abrindo compartilhamento"/> Abrindo compartilhamento...</p></div>:error?<div className="public-share-error"><CircleAlert size={19}/>{error}</div>:data&&<>
 <div className="public-drive-intro"><div className="public-drive-folder-icon">{data.kind==='folder'?<Folder size={27}/>:<File size={27}/>}</div><div><span>COMPARTILHADO COM VOCÊ</span><h1>{data.name}</h1><p>{data.mode==='download'?'Acesso de download':data.kind==='folder'?'Navegue pelas pastas e abra os arquivos disponíveis':'Visualize e baixe este arquivo'}</p></div><a className="public-drive-download" href={endpoint+'/download'}><Download size={17}/>{data.kind==='folder'?'Baixar tudo em ZIP':'Baixar arquivo'}</a></div>
 {data.mode==='view'&&data.kind==='folder'&&<>
 <div className="public-drive-toolbar"><div className="public-drive-breadcrumbs"><button title="Voltar à raiz" onClick={()=>goFolder(root)}><Home size={16}/></button><ChevronRight size={15}/><button onClick={()=>goFolder(root)} title={data.name}>{data.name}</button>{parents.map(p=><React.Fragment key={p.id}><ChevronRight size={15}/><button onClick={()=>goFolder(p.id)} title={p.name}>{p.name}</button></React.Fragment>)}</div><span className="public-drive-count">{visible.length} {visible.length===1?'item':'itens'}</span></div>
 <div className="public-drive-tools"><button className="public-drive-back" onClick={()=>goFolder(up)} disabled={current===root}><ArrowLeft size={17}/> Voltar</button><div className="public-drive-search"><Search size={16}/><input placeholder="Buscar nesta pasta..." value={search} onChange={e=>setSearch(e.target.value)}/></div><div className="public-drive-switch"><button title="Modo lista" className={view==='list'?'on':''} onClick={()=>setView('list')}><List size={17}/></button><button title="Modo grade" className={view==='grid'?'on':''} onClick={()=>setView('grid')}><Grid2X2 size={17}/></button></div></div>
 <div className={'public-drive-files '+(view==='grid'?'as-grid':'as-list')}>
 {visible.length?visible.map(item=><div className={'public-drive-entry '+(item.kind==='folder'?'is-folder':'')} key={item.id}>
 <button className="public-drive-open" title={item.kind==='folder'?'Abrir '+item.name:'Visualizar '+item.name} onClick={()=>item.kind==='folder'?goFolder(item.id):setOpened(item)}><span className="public-drive-entry-icon">{item.kind==='folder'?<Folder size={view==='grid'?35:21} fill="#80aaf0" color="#a7caff" strokeWidth={1.4}/>:image(item)?<SharedMediaThumb src={mediaUrl(item)+'&thumb=1'}/>:video(item)?<SharedMediaThumb src={mediaUrl(item)} video/>:<File size={view==='grid'?33:21}/>}</span><span className="public-drive-entry-info"><strong>{item.name}</strong><small>{item.kind==='folder'?'Pasta':size(item.size||0)}</small></span></button>
 {item.kind==='folder'?<button className="public-drive-entry-action" title="Abrir pasta" onClick={()=>goFolder(item.id)}><ChevronRight size={18}/></button>:<a className="public-drive-entry-action" title="Baixar arquivo" href={endpoint+'/file/'+encodeURIComponent(item.id)}><Download size={18}/></a>}
 </div>):<div className="public-drive-empty"><Folder size={36}/><strong>{search?'Nenhum resultado':'Esta pasta está vazia'}</strong><span>{search?'Tente outro nome de arquivo.':'Volte para explorar outras pastas compartilhadas.'}</span></div>}
 </div></>}
 {data.mode==='view'&&data.kind==='file'&&image(data)&&<div className="public-share-image"><SharedMediaDisplay src={endpoint+'/media?access='+encodeURIComponent(data.media_ticket||'')} statusUrl={endpoint+'/media-status'} name={data.name}/></div>}
 {data.mode==='view'&&data.kind==='file'&&video(data)&&<div className="public-share-image"><SharedMediaDisplay src={endpoint+'/media?access='+encodeURIComponent(data.media_ticket||'')} statusUrl={endpoint+'/media-status'} name={data.name} video/></div>}
 {data.mode==='download'&&<div className="public-drive-direct"><Download size={27}/><strong>Seu download está disponível</strong><p>Clique em Baixar para salvar {data.kind==='folder'?'a pasta compactada':'o arquivo'} neste computador.</p></div>}
 <div className="public-drive-footer"><span><Clock3 size={14}/> Disponível até {new Date(data.expires*1000).toLocaleString('pt-BR')}</span><span>Compartilhamento local · O computador do proprietário precisa estar ligado</span></div>
 {opened&&<div className="public-file-overlay" role="presentation" onClick={()=>setOpened(null)}><div className="public-file-preview" role="dialog" aria-modal="true" aria-label={'Visualizar '+opened.name} onClick={e=>e.stopPropagation()}><div className="public-file-preview-top"><span title={opened.name}><File size={17}/>{opened.name}</span><div><a href={endpoint+'/file/'+encodeURIComponent(opened.id)}><Download size={17}/> Baixar</a><button aria-label="Fechar visualização" onClick={()=>setOpened(null)}><X size={19}/></button></div></div><div className="public-file-preview-content">{image(opened)?<SharedMediaDisplay src={mediaUrl(opened)} statusUrl={endpoint+'/media-status?file_id='+encodeURIComponent(opened.id)} name={opened.name}/>:video(opened)?<SharedMediaDisplay src={mediaUrl(opened)} statusUrl={endpoint+'/media-status?file_id='+encodeURIComponent(opened.id)} name={opened.name} video/>:<div className="public-file-no-preview"><File size={54}/><strong>Prévia indisponível</strong><span>Baixe o arquivo para abri-lo no seu dispositivo.</span></div>}</div></div></div>}
 </>}
 </div></main>;
}
function ShareDialog({item,onClose,onToast}){
 const [mode,setMode]=useState(item.kind==='folder'?'view':'download'),[expires,setExpires]=useState('24'),[busy,setBusy]=useState(false),[created,setCreated]=useState(null),[existing,setExisting]=useState([]),[error,setError]=useState('');
 async function refreshLinks(){try{const r=await fetch('http://127.0.0.1:8000/api/share');if(!r.ok)return;const data=await r.json();setExisting((data.links||[]).filter(x=>x.item_id===item.id&&!x.revoked&&x.expires>Date.now()/1000))}catch{}}
 useEffect(()=>{refreshLinks()},[item.id]);
 async function createLink(){
  setBusy(true);setError('');
  try{
   const response=await fetch('http://127.0.0.1:8000/api/share',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_id:item.id,mode,expires_hours:Number(expires)})});
   const result=await response.json();if(!response.ok)throw Error(result.detail||'Não foi possível criar o link.');
   setCreated({...result,url:window.location.origin+'/?'+(mode==='embed'?'embed':'share')+'='+encodeURIComponent(result.token)});
   await refreshLinks();
   onToast?.({kind:'success',message:'Link local criado.'});
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function copyLink(){try{await navigator.clipboard.writeText(created.url);onToast?.({kind:'success',message:'Link copiado.'})}catch{setError('Não foi possível copiar automaticamente. Selecione o endereço no campo.')}}
 async function revoke(id){try{const response=await fetch('http://127.0.0.1:8000/api/share/'+id,{method:'DELETE'});if(!response.ok)throw Error('Falha ao revogar.');if(created?.id===id)setCreated(null);await refreshLinks();onToast?.({kind:'success',message:'Link revogado.'})}catch(e){setError(e.message)}}
 return <div className="move-backdrop" role="presentation" onClick={()=>!busy&&onClose()}><div className="move-dialog share-dialog" role="dialog" aria-modal="true" aria-labelledby="share-dialog-title" onClick={e=>e.stopPropagation()}>
 <div className="move-dialog-header"><div className="share-dialog-heading"><span className="share-dialog-heading-icon"><Users size={21}/></span><div><h3 id="share-dialog-title">Compartilhar {item.kind==='folder'?'pasta':'arquivo'}</h3><p>Configure como outras pessoas poderão acessar</p></div></div><button className="move-close" aria-label="Fechar" onClick={onClose}><X size={19}/></button></div>
 <div className="share-dialog-body"><div className="share-dialog-file"><span className="share-dialog-file-icon">{item.kind==='folder'?<Folder size={23}/>:<File size={23}/>}</span><div><strong title={item.name}>{item.name}</strong><small>{item.kind==='folder'?'Pasta do Meu Drive':'Arquivo do Meu Drive'}</small></div><Check size={17}/></div><div className="share-local-note"><CircleAlert size={17}/> Links de teste neste computador. Compartilhamento pela internet requer um serviço HTTPS separado e protegido.</div>
 <div className="share-dialog-label"><strong>Tipo de acesso</strong><small>Escolha o que o destinatário poderá fazer</small></div><div className="share-mode-grid"><button className={mode==='download'?'chosen':''} onClick={()=>{setMode('download');setCreated(null)}}><Download size={20}/><strong>Download</strong><small>Um clique para baixar {item.kind==='folder'?'a pasta em ZIP':'o arquivo'}</small></button><button className={mode==='view'?'chosen':''} onClick={()=>{setMode('view');setCreated(null)}}><Eye size={20}/><strong>Compartilhado</strong><small>{item.kind==='folder'?'Explorar pastas, visualizar e baixar':'Visualizar antes de baixar'}</small></button></div>
 {item.kind==='file'&&/\.(png|jpe?g|gif|webp|mp4|webm|m4v)$/i.test(item.name)&&<button type="button" className={'share-embed-choice '+(mode==='embed'?'chosen':'')} onClick={()=>{setMode('embed');setCreated(null)}}><Code size={17}/><span><strong>Integração (embed)</strong><small>Incorpore a imagem ou vídeo em outra página.</small></span><ChevronRight size={16}/></button>}<label htmlFor="share-expiry" className="share-expiry-label"><Clock3 size={15}/> O link expira em</label><select className="dc-native-select" id="share-expiry" value={expires} onChange={e=>setExpires(e.target.value)}><option value="1">1 hora</option><option value="24">24 horas</option><option value="168">7 dias</option></select>
 {created&&<div className="share-result"><label><Check size={16}/> Link criado</label><div><input readOnly value={created.url} aria-label="Link criado" onFocus={e=>e.target.select()}/><button onClick={copyLink}><Check size={16}/> Copiar</button></div>{mode==='embed'&&<div className="share-embed-snippet"><label>Código para incorporar o mesmo link</label><textarea readOnly aria-label="Código embed" value={'<iframe src="'+created.url+'" width="640" height="360" loading="lazy" allow="fullscreen" style="border:0;border-radius:12px;" title="'+item.name.replace(/"/g,'')+'"></iframe>'} onFocus={e=>e.target.select()}/><button onClick={()=>{const snippet='<iframe src="'+created.url+'" width="640" height="360" loading="lazy" allow="fullscreen" style="border:0;border-radius:12px;"></iframe>';navigator.clipboard.writeText(snippet).then(()=>onToast?.({kind:'success',message:'Código embed copiado'})).catch(()=>setError('Selecione e copie o código manualmente.'))}}><Code size={15}/> Copiar código</button></div>}</div>}
 {error&&<div className="public-share-error">{error}</div>}
 {existing.length>0&&<div className="share-existing"><strong>Links ativos</strong>{existing.map(link=><div key={link.id}><span>{link.mode==='download'?'Download':link.mode==='embed'?'Integração':'Compartilhado'} • até {new Date(link.expires*1000).toLocaleDateString('pt-BR')}</span><button onClick={()=>revoke(link.id)}>Revogar</button></div>)}</div>}
 </div><div className="move-footer"><button onClick={onClose}>Concluir</button><button className="move-confirm" disabled={busy} onClick={createLink}><Users size={16}/>{busy?'Criando...':'Gerar novo link'}</button></div></div></div>
}
function DriveCloudLoader({size=58,label='Carregando...'}) {
 return <span className="dc-cloud-loader" role="status" aria-label={label} style={{'--cloud-size':size+'px'}}>
  <svg viewBox="0 0 96 64" aria-hidden="true" fill="none" xmlns="http://www.w3.org/2000/svg">
   <path className="dc-cloud-outline" d="M25 52h48c11 0 18-7.5 18-17 0-9.2-7.1-16.5-16.5-16.5-1.8 0-3.6.3-5.2.8C65.7 10.7 57.8 5 48 5 35.1 5 24.4 14.7 23.2 27.2 13.1 27.2 5 32.8 5 40.3 5 47.7 11 52 25 52Z"/>
   <path className="dc-cloud-running" d="M25 52h48c11 0 18-7.5 18-17 0-9.2-7.1-16.5-16.5-16.5-1.8 0-3.6.3-5.2.8C65.7 10.7 57.8 5 48 5 35.1 5 24.4 14.7 23.2 27.2 13.1 27.2 5 32.8 5 40.3 5 47.7 11 52 25 52Z"/>
  </svg>
 </span>
}
function DriveBrandLoader(){
 return <div className="dc-brand-loader" role="status" aria-label="Abrindo Drive Cloud">
  <svg className="dc-brand-loader-ring" viewBox="0 0 120 120" aria-hidden="true">
   <circle className="dc-brand-ring-track" cx="60" cy="60" r="52"/>
   <circle className="dc-brand-ring-active" cx="60" cy="60" r="52"/>
  </svg>
  <img src="/drive-cloud-logo.svg" alt=""/>
 </div>
}
function DriveLoadingSkeleton({layout='grid',home=false}){
 const count=home?4:layout==='grid'?8:7;
 return <div className="dc-loading-screen" role="status" aria-label="Carregando seus arquivos" aria-busy="true">
 {home&&<div className="dc-loading-home"><div className="dc-shimmer dc-loading-label"/><div className="dc-loading-recent">{[0,1,2].map(i=><div key={i} className="dc-shimmer dc-loading-recent-item"/>)}</div></div>}
 <div className="dc-loading-top"><div className="dc-shimmer dc-loading-label"/><div className="dc-shimmer dc-loading-label short"/></div>
 {layout==='grid'?<div className="dc-loading-grid">{Array.from({length:count},(_,i)=><div className="dc-loading-card" key={i}><div className="dc-shimmer dc-loading-art"/><div className="dc-shimmer dc-loading-line"/><div className="dc-shimmer dc-loading-line tiny"/></div>)}</div>:<div className="dc-loading-rows">{Array.from({length:count},(_,i)=><div className="dc-loading-row" key={i}><div className="dc-shimmer dc-loading-row-icon"/><div className="dc-shimmer dc-loading-row-label"/><div className="dc-shimmer dc-loading-row-size"/></div>)}</div>}
 <div className="dc-loading-caption"><DriveCloudLoader size={48} label="Preparando seus arquivos"/> <span>Preparando seus arquivos...</span></div>
 </div>
}
function CloudFiles({mode='files',globalSearch='',onToast,onDeletionProgress,createFolderToken=0,onCatalogChange,onFolderChange,folderTarget,onInitialReady}){
const [preview,setPreview]=useState(null),[previewError,setPreviewError]=useState(false),[trayVisible,setTrayVisible]=useState(true),[nodes,setNodes]=useState([]),[folder,setFolder]=useState(null),[layout,setLayout]=useState(readDriveLayout),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[selected,setSelected]=useState([]),[menu,setMenu]=useState(null),[moveTargets,setMoveTargets]=useState(null),[moveDestination,setMoveDestination]=useState(''),[moveNewFolder,setMoveNewFolder]=useState(false),[moveFolderName,setMoveFolderName]=useState(''),[folderDialog,setFolderDialog]=useState(false),[folderName,setFolderName]=useState(''),[folderBusy,setFolderBusy]=useState(false),[drag,setDrag]=useState(false),[jobs,setJobs]=useState([]),[panel,setPanel]=useState(false),[tab,setTab]=useState('all'),[deleteConfirm,setDeleteConfirm]=useState(null),[deleteJob,setDeleteJob]=useState(null),[catalogCheck,setCatalogCheck]=useState(null),[catalogBusy,setCatalogBusy]=useState(false),[zipProgress,setZipProgress]=useState(null),[shareItem,setShareItem]=useState(null);
const uploader=useRef(null),catalogPicker=useRef(null),active=useRef(null),cancelAll=useRef(false),cancelDeletion=useRef(false);
useEffect(()=>{onDeletionProgress?.(deleteJob?{...deleteJob,cancel:stopDeletion}:null)},[deleteJob]);
const trash=mode==='trash';
useEffect(()=>{if(createFolderToken>0){setFolderName('');setFolderDialog(true)}},[createFolderToken]);
useEffect(()=>{setSelected([]);setMenu(null);if(mode!=='files')setFolder(null)},[mode]);
useEffect(()=>{localStorage.setItem('dc-file-layout',layout)},[layout]);
useEffect(()=>{const listener=event=>setLayout(event.detail==='grid'?'grid':'list');window.addEventListener('drive-layout-updated',listener);return()=>window.removeEventListener('drive-layout-updated',listener)},[]);
useEffect(()=>{if(folderTarget){setFolder(folderTarget.id||null);setSelected([])}},[folderTarget?.nonce]);
useEffect(()=>{onFolderChange?.(folder)},[folder]);
useEffect(()=>{onCatalogChange?.(nodes)},[nodes]);
const base='http://127.0.0.1:8000/api/cloud';
async function request(path,options){const r=await fetch(base+path,options);if(!r.ok){let detail='Erro HTTP '+r.status;try{const e=await r.json();detail=typeof e.detail==='string'?e.detail:detail}catch{}throw Error(detail)}return r}
async function reload(){try{const r=await request('/items');setNodes((await r.json()).items);setError('')}catch(e){setError(e.message)}finally{setLoading(false)}}
useEffect(()=>{reload()},[]);
useEffect(()=>{if(!loading)onInitialReady?.()},[loading,onInitialReady]);
useEffect(()=>{if(notice){onToast?.({kind:'success',message:notice});setNotice('')}},[notice]);
useEffect(()=>{if(error){onToast?.({kind:'error',message:error,duration:6500});setError('')}},[error]);
const breadcrumb=[];let current=folder;for(let n=0;current&&n<30;n++){const item=nodes.find(i=>i.id===current&&i.kind==='folder');if(!item)break;breadcrumb.unshift(item);current=item.parent}
const queryText=globalSearch.trim().toLocaleLowerCase('pt-BR');
const visible=nodes.filter(i=>trash?!!i.trashed:!i.trashed&&(queryText?true:mode==='home'?true:mode==='recent'?i.kind==='file':mode==='starred'?!!i.starred:i.parent===folder)).filter(i=>i.name.toLocaleLowerCase('pt-BR').includes(queryText)).sort((a,b)=>mode==='home'||mode==='recent'||queryText?b.created-a.created:(a.kind===b.kind?a.name.localeCompare(b.name,'pt-BR'):a.kind==='folder'?-1:1)).slice(0,mode==='home'&&!queryText?16:undefined);
const homeRecent=nodes.filter(i=>!i.trashed&&i.kind==='file').sort((a,b)=>b.created-a.created).slice(0,5);
const homeFavorites=nodes.filter(i=>!i.trashed&&i.starred).sort((a,b)=>b.created-a.created).slice(0,5);
const chosen=visible.filter(i=>selected.includes(i.id));
const setJob=(id,values)=>setJobs(j=>j.map(x=>x.id===id?{...x,...values}:x));
function addFiles(inputFiles){
 const files=Array.from(inputFiles||[]);if(!files.length)return;
 const valid=files.filter(file=>file.size<=20*1024*1024);
 const rejected=files.filter(file=>file.size>20*1024*1024);
 if(rejected.length){
   onToast?.({kind:'error',message:rejected.length===1?'Arquivo excede o limite atual de 20 MB: '+rejected[0].name:rejected.length+' arquivos excedem o limite atual de 20 MB.',duration:6500});
 }
 if(!valid.length){
   // Validation errors show only a toast. Never open an empty transfer window.
   if(!busy)setTrayVisible(false);
   if(uploader.current)uploader.current.value='';
   return;
 }
 cancelAll.current=false;
 const entries=valid.map(file=>({id:crypto.randomUUID(),file,name:file.name,progress:0,status:'queued'}));
 setJobs(j=>[...j,...entries]);setPanel(true);
 runQueue(entries);
}
async function runQueue(entries){
 setBusy(true);
 for(const entry of entries){
  if(cancelAll.current){setJob(entry.id,{status:'cancelled'});continue}
  setJob(entry.id,{status:'uploading',progress:0,detail:'Preparando envio...'});
  setTrayVisible(true);
  let pollTimer=null, polling=false, finished=false;
  try{
   await new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    active.current=xhr;
    xhr.open('POST',base+'/upload');
    const beginPolling=()=>{
      if(pollTimer)return;
      pollTimer=setInterval(async()=>{
       if(polling||finished)return;
       polling=true;
       try{
        const response=await fetch(base+'/upload-progress/'+encodeURIComponent(entry.id),{cache:'no-store'});
        if(!response.ok)return;
        const status=await response.json();
        if(finished)return;
        if(status.stage==='telegram'&&status.total>0){
          const uploaded=Math.min(1,Math.max(0,status.sent/status.total));
          setJob(entry.id,{progress:Math.min(95,Math.round(10+uploaded*85)),detail:'Enviando ao Telegram...'});
        }else if(status.stage==='catalog'){
          setJob(entry.id,{progress:95,detail:'Confirmando arquivo e salvando catálogo...'});
        }
       }catch{}finally{polling=false}
      },350);
    };
    xhr.upload.onprogress=e=>{
      if(e.lengthComputable){
       setJob(entry.id,{progress:Math.min(10,Math.round((e.loaded/e.total)*10)),detail:'Transferindo para o backend local...'});
      }
    };
    xhr.upload.onload=()=>{
      setJob(entry.id,{progress:10,detail:'Aguardando envio ao Telegram...'});
      beginPolling();
    };
    xhr.onload=()=>{
      if(xhr.status>=200&&xhr.status<300)resolve();
      else{let detail='Erro '+xhr.status;try{detail=JSON.parse(xhr.responseText).detail||detail}catch{}reject(Error(detail))}
    };
    xhr.onerror=()=>reject(Error('Falha de rede'));
    xhr.onabort=()=>reject(Error('Solicitação interrompida'));
    const body=new FormData();
    body.append('file',entry.file);
    body.append('upload_id',entry.id);
    if(folder)body.append('parent',folder);
    xhr.send(body);
   });
   finished=true;
   setJob(entry.id,{status:'completed',progress:100,detail:'Arquivo confirmado no Telegram'});
   onToast?.({kind:'success',message:'Arquivo enviado: '+entry.name});
  }catch(e){
   finished=true;
   setJob(entry.id,{status:cancelAll.current?'cancelled':'failed',detail:e.message});
   if(!cancelAll.current)onToast?.({kind:'error',message:'Falha no envio de '+entry.name+': '+e.message,duration:6000});
  }finally{
   finished=true;
   if(pollTimer)clearInterval(pollTimer);
   active.current=null;
   await reload();
  }
 }
 setBusy(false);
 if(uploader.current)uploader.current.value='';
}
function stopUploads(){cancelAll.current=true;active.current?.abort();setJobs(j=>j.map(x=>x.status==='queued'?{...x,status:'cancelled'}:x))}
function newFolder(){setFolderName('');setFolderDialog(true)}
async function submitNewFolder(){
 const name=folderName.trim();if(!name||folderBusy)return;
 if(name.includes('/')||name.includes('\\')){setError('O nome da pasta não pode conter barras.');return}
 setFolderBusy(true);
 try{
  await request('/folders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,parent:folder||null})});
  await reload();
  setFolderDialog(false);setFolderName('');
  onToast?.({kind:'success',message:'Pasta criada: '+name});
 }catch(e){setError(e.message)}
 finally{setFolderBusy(false)}
}
async function downloadFolderZip(item){
 if(zipProgress){onToast?.({kind:'info',message:'Já há uma compactação em andamento nesta janela.'});return}
 setMenu(null);
 try{
  const started=await request('/folders/'+encodeURIComponent(item.id)+'/zip',{method:'POST'});
  const data=await started.json();
  setZipProgress({id:data.job_id,name:item.name,done:0,count:data.count,state:'preparing'});
  const startedAt=Date.now();
  for(;;){
   if(Date.now()-startedAt>15*60*1000)throw Error('Tempo limite preparando o ZIP. Tente novamente.');
   await new Promise(resolve=>setTimeout(resolve,600));
   const res=await request('/zip/'+encodeURIComponent(data.job_id));
   const status=await res.json();
   setZipProgress({id:data.job_id,name:item.name,...status});
   if(status.state==='failed')throw Error(status.error||'Não foi possível compactar a pasta.');
   if(status.state==='ready'){
    const a=document.createElement('a');
    a.href=base+'/zip/'+encodeURIComponent(data.job_id)+'/download';
    a.download=status.name||item.name+'.zip';
    document.body.append(a);a.click();a.remove();
    setZipProgress(null);
    onToast?.({kind:'success',message:'ZIP preparado. Download iniciado: '+(status.name||item.name+'.zip')});
    return;
   }
  }
 }catch(e){setZipProgress(null);onToast?.({kind:'error',message:'Falha ao compactar pasta: '+e.message,duration:6500})}
}
async function download(item){if(item.kind==='folder')return downloadFolderZip(item);try{setError('');const r=await request('/download/'+encodeURIComponent(item.id));const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=item.name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),15000);onToast?.({kind:'success',message:'Download iniciado: '+item.name})}catch(e){setError(e.message)}}
async function open(item){if(item.kind==='folder'){setFolder(item.id);setSelected([]);setMenu(null)}else if(isCloudImage(item)||isCloudVideo(item)){setPreview(item);setPreviewError(false);setMenu(null)}else await download(item)}
async function patch(item,data){const r=await request('/items/'+encodeURIComponent(item.id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});await r.json()}
async function action(kind,targets){setMenu(null);if(!targets.length)return;try{if(kind==='download'){for(const item of targets)await download(item);return}
if(kind==='rename'){const name=prompt('Novo nome:',targets[0].name);if(!name?.trim())return;await patch(targets[0],{name:name.trim()})}
if(kind==='share'){setShareItem(targets[0]);return}
if(kind==='move'){setMoveTargets(targets);setMoveDestination('');setMoveNewFolder(false);setMoveFolderName('');return}
if(kind==='trash'||kind==='permanent'){setDeleteConfirm({kind,targets});return}
if(kind==='trash'||kind==='restore'){for(const item of targets)await patch(item,{trashed:kind==='trash'?true:false})}
if(kind==='favorite'){for(const item of targets)await patch(item,{starred:!item.starred})}
await reload();setSelected([]);if(kind==='trash'){onToast?.({kind:'success',message:targets.length===1?'Arquivo movido para a lixeira':`${targets.length} itens movidos para a lixeira`,duration:6000,undo:async()=>{try{for(const item of targets)await patch(item,{trashed:false});await reload();onToast?.({kind:'success',message:'Arquivos restaurados'})}catch(e){onToast?.({kind:'error',message:e.message})}}})}else setNotice(kind==='restore'?'Arquivo restaurado':kind==='favorite'?'Favoritos atualizados':'Alterações salvas')}catch(e){setError(e.message)}}
async function confirmDeletion(){
 const req=deleteConfirm;if(!req)return;setDeleteConfirm(null);setSelected([]);
 cancelDeletion.current=false;
 const targets=req.targets.slice();
 setDeleteJob({kind:req.kind,total:targets.length,completed:0,current:'',state:'running'});
 let completed=0,failed=false;
 for(const item of targets){
   if(cancelDeletion.current)break;
   setDeleteJob(j=>({...j,current:item.name}));
   try{
     if(req.kind==='permanent')await request('/items/'+encodeURIComponent(item.id)+'/permanent',{method:'DELETE'});
     else await patch(item,{trashed:true});
     completed++;setDeleteJob(j=>({...j,completed}));
     await reload();
   }catch(e){
     failed=true;onToast?.({kind:'error',message:'Falha ao excluir '+item.name+': '+e.message,duration:6500});
     break;
   }
 }
 const cancelled=cancelDeletion.current;
 setDeleteJob(null);
 await reload();
 if(!failed){
   if(req.kind==='permanent')onToast?.({kind:cancelled?'info':'success',message:cancelled?'Exclusão interrompida. '+completed+' item(ns) excluído(s).':completed+' item(ns) excluído(s) definitivamente.'});
   else onToast?.({kind:cancelled?'info':'success',message:cancelled?'Movimentação interrompida após '+completed+' item(ns).':completed+' item(ns) movido(s) para a lixeira.'});
 }
}
function stopDeletion(){cancelDeletion.current=true;setDeleteJob(j=>j?({...j,state:'cancelling'}):null)}
async function exportCatalog(){try{const r=await request('/catalog/export');const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='drive-cloud-catalog-'+new Date().toISOString().slice(0,10)+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);onToast?.({kind:'success',message:'Catálogo exportado. Guarde este arquivo em local seguro.'})}catch(e){setError(e.message)}}
async function checkCatalog(file){
 if(!file)return;
 setCatalogBusy(true);setError('');
 try{
  const body=new FormData();body.append('file',file);body.append('dry_run','true');
  const result=await (await request('/catalog/import',{method:'POST',body})).json();
  setCatalogCheck({file,result});
 }catch(e){setError(e.message);setCatalogCheck(null)}
 finally{setCatalogBusy(false);if(catalogPicker.current)catalogPicker.current.value=''}
}
async function restoreCatalog(){
 if(!catalogCheck||catalogBusy)return;
 setCatalogBusy(true);
 try{
  const body=new FormData();body.append('file',catalogCheck.file);body.append('dry_run','false');
  const result=await (await request('/catalog/import',{method:'POST',body})).json();
  setCatalogCheck(null);await reload();
  onToast?.({kind:'success',message:result.imported+' registro(s) recuperado(s) com segurança.'});
 }catch(e){setError(e.message)}
 finally{setCatalogBusy(false)}
}
async function createMoveFolder(){
 const name=moveFolderName.trim();
 if(!name||busy)return;
 setBusy(true);
 try{
  const response=await request('/folders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,parent:moveDestination||null})});
  const created=await response.json();
  await reload();
  setMoveNewFolder(false);
  setMoveFolderName('');
  setMoveDestination(created.id);
  onToast?.({kind:'success',message:'Pasta criada: '+name});
 }catch(e){setError(e.message)}finally{setBusy(false)}
}
function goMoveParent(){
 if(!moveDestination)return;
 const item=nodes.find(x=>x.id===moveDestination);
 setMoveDestination(item?.parent||'');
 setMoveNewFolder(false);
 setMoveFolderName('');
}
async function confirmMove(){if(!moveTargets)return;setBusy(true);setError('');try{for(const item of moveTargets)await patch(item,{parent:moveDestination||null});await reload();setSelected([]);setMoveTargets(null);setNotice('Arquivo(s) movido(s)')}catch(e){setError(e.message)}finally{setBusy(false)}}
function toggle(id){setSelected(old=>old.includes(id)?old.filter(x=>x!==id):[...old,id])}
const completed=jobs.filter(x=>x.status==='completed').length;
const failures=jobs.filter(x=>x.status==='failed').length;
const uploadingNow=jobs.filter(x=>x.status==='uploading'||x.status==='queued').length;
const filteredJobs=jobs.filter(x=>tab==='all'||(tab==='completed'&&x.status==='completed')||(tab==='failed'&&['failed','cancelled'].includes(x.status))||(tab==='pending'&&['queued','uploading'].includes(x.status)));
const moveBreadcrumbs=[];let moveCurrent=moveDestination;
for(let depth=0;moveCurrent&&depth<40;depth++){
 const item=nodes.find(x=>x.id===moveCurrent&&x.kind==='folder');
 if(!item)break;
 moveBreadcrumbs.unshift(item);
 moveCurrent=item.parent;
}
const forbiddenMoveFolder=id=>{
 if(!moveTargets)return false;
 if(moveTargets.some(t=>t.id===id))return true;
 let cursor=id;
 for(let depth=0;cursor&&depth<40;depth++){
  const parent=nodes.find(n=>n.id===cursor)?.parent;
  if(!parent)break;
  if(moveTargets.some(t=>t.id===parent))return true;
  cursor=parent;
 }
 return false;
};
const availableMoveFolders=nodes.filter(x=>x.kind==='folder'&&!x.trashed&&(x.parent||'')===moveDestination&&!forbiddenMoveFolder(x.id)).sort((a,b)=>a.name.localeCompare(b.name,'pt-BR'));

return <section className="cloud-page" onDragEnter={e=>{e.preventDefault();if(e.dataTransfer?.types?.includes('Files'))setDrag(true)}} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();setDrag(false);if(e.dataTransfer?.files?.length)addFiles(e.dataTransfer.files)}}>
{mode==='home'&&!queryText&&!loading&&<div className="home-sections">
<section><div className="home-section-title"><Clock3 size={17}/><h3>Recentes</h3><span>Últimos arquivos enviados</span></div><div className="home-quick-list">{homeRecent.length?homeRecent.map(item=><button key={item.id} onClick={()=>open(item)}><span className="home-quick-thumb"><CloudThumbnail item={item} compact/></span><span className="home-quick-name">{item.name}</span><small>{date(item.created)}</small></button>):<p>Seus arquivos recentes aparecerão aqui.</p>}</div></section>
<section><div className="home-section-title"><Star size={17}/><h3>Favoritos</h3><span>Acesso rápido</span></div><div className="home-quick-list">{homeFavorites.length?homeFavorites.map(item=><button key={item.id} onClick={()=>open(item)}><span className="home-quick-thumb"><CloudThumbnail item={item} compact/></span><span className="home-quick-name">{item.name}</span><Star size={15} fill="#e2c16f" color="#e2c16f"/></button>):<p>Marque arquivos com a estrela para acessá-los rapidamente.</p>}</div></section>
</div>}
<div className="cloud-toolbar"><div className="cloud-crumb"><button onClick={()=>{setFolder(null);setSelected([])}}>{mode==='home'?'Visão geral':mode==='recent'?'Recentes':mode==='starred'?'Favoritos':mode==='trash'?'Lixeira':'Meu Drive'}</button>{breadcrumb.map(p=><React.Fragment key={p.id}><ChevronRight size={14}/><button onClick={()=>{setFolder(p.id);setSelected([])}}>{p.name}</button></React.Fragment>)}</div><div className="cloud-controls">{!trash&&<><button disabled={busy} onClick={newFolder}><FolderPlus size={16}/> Nova pasta</button><button className="cloud-primary" disabled={busy} onClick={()=>uploader.current?.click()}><Upload size={16}/> Upload</button></>}{mode==='files'&&<><button title="Exportar catálogo para backup" aria-label="Exportar catálogo" onClick={exportCatalog}><DatabaseBackup size={16}/></button><button title="Restaurar catálogo exportado" aria-label="Restaurar catálogo" disabled={catalogBusy} onClick={()=>catalogPicker.current?.click()}><RotateCcw size={16}/></button></>}<button title="Atualizar" onClick={reload}><RefreshCw size={16}/></button><div className="toggle"><button title="Grade" className={layout==='grid'?'chosen':''} onClick={()=>setLayout('grid')}><Grid2X2 size={17}/></button><button title="Lista" className={layout==='list'?'chosen':''} onClick={()=>setLayout('list')}><List size={17}/></button></div></div></div>
<input type="file" multiple hidden ref={uploader} onChange={e=>addFiles(e.target.files)}/><input type="file" accept=".json,application/json" hidden ref={catalogPicker} onChange={e=>checkCatalog(e.target.files?.[0])}/>
<div className="selection-zone"><div className={'bulkbar '+(selected.length?'is-visible':'')} aria-hidden={!selected.length}><div className="bulk-actions"><button className="bulk-primary" disabled={!selected.length} onClick={()=>action('download',chosen)}><Download size={16}/> Baixar</button>{trash?<><button disabled={!selected.length} onClick={()=>action('restore',chosen)}>Restaurar</button><button className="danger-action" disabled={!selected.length} onClick={()=>action('permanent',chosen)}><Trash2 size={15}/> Excluir definitivamente</button></>:<>{selected.length===1&&<button onClick={()=>action('share',chosen)}><Users size={15}/> Compartilhar</button>}<button disabled={!selected.length} onClick={()=>action('move',chosen)}>Mover</button><button className="danger-action" disabled={!selected.length} onClick={()=>action('trash',chosen)}><Trash2 size={15}/> Excluir</button></>}<button disabled={!selected.length} onClick={()=>setSelected([])}>Limpar</button></div><strong>{selected.length} selecionado{selected.length===1?'':'s'}</strong></div></div>

{loading?<DriveLoadingSkeleton layout={layout} home={mode==='home'}/>:visible.length===0?<div className="empty"><Folder size={43}/><h3>{trash?'Lixeira vazia':mode==='starred'?'Nenhum favorito ainda':mode==='recent'?'Nenhum arquivo recente':mode==='home'?'Seu Drive está pronto':'Esta pasta está vazia'}</h3><p>{mode==='starred'?'Marque uma estrela em qualquer arquivo ou pasta para encontrá-lo aqui.':mode==='files'?'Arraste arquivos para esta janela ou clique em Upload.':'Seus arquivos armazenados no Telegram aparecerão aqui.'}</p></div>:layout==='grid'?<><div className="cloud-selectall"><label><input type="checkbox" checked={selected.length===visible.length&&visible.length>0} onChange={e=>setSelected(e.target.checked?visible.map(i=>i.id):[])}/> Selecionar tudo</label></div><div className="grid">{visible.map(item=><article key={item.id} className={'tile cloud-tile '+(selected.includes(item.id)?'selected':'')}><label className="tile-select"><input type="checkbox" checked={selected.includes(item.id)} onChange={()=>toggle(item.id)} aria-label={'Selecionar '+item.name}/></label><div className="tile-menu"><button className={'file-menu-trigger '+(menu===item.id?'is-open':'')} title="Mais opções" aria-label={'Opções '+item.name} aria-expanded={menu===item.id} onClick={()=>setMenu(menu===item.id?null:item.id)}><MoreHorizontal size={19}/></button>{menu===item.id&&<><button className="file-menu-dismiss" aria-label="Fechar menu" onClick={()=>setMenu(null)}/><div className="file-menu" role="menu"><div className="file-menu-title" title={item.name}>{item.name}</div>{<button role="menuitem" onClick={()=>action('download',[item])}><Download size={17}/> {item.kind==='folder'?'Baixar como ZIP':'Baixar'}</button>}{(isCloudImage(item)||isCloudVideo(item))&&<button role="menuitem" onClick={()=>{setPreview(item);setPreviewError(false);setMenu(null)}}><Eye size={17}/> {isCloudVideo(item)?'Reproduzir vídeo':'Visualizar imagem'}</button>}<div className="file-menu-separator"/>{!trash&&<button role="menuitem" onClick={()=>action('share',[item])}><Users size={17}/> Compartilhar link</button>}<button role="menuitem" onClick={()=>action('favorite',[item])}><Star size={17} fill={item.starred?'#e2c16f':'none'}/> {item.starred?'Remover dos favoritos':'Adicionar aos favoritos'}</button><button role="menuitem" onClick={()=>action('rename',[item])}><Pencil size={17}/> Renomear</button><button role="menuitem" onClick={()=>action('move',[item])}><MoveRight size={17}/> Mover para...</button><div className="file-menu-separator"/>{trash?<><button role="menuitem" onClick={()=>action('restore',[item])}><RotateCcw size={17}/> Restaurar</button><button role="menuitem" className="danger-action" onClick={()=>action('permanent',[item])}><Trash2 size={17}/> Excluir definitivamente</button></>:<button role="menuitem" className="danger-action" onClick={()=>action('trash',[item])}><Trash2 size={17}/> Mover para lixeira</button>}</div></>}</div><div className={'tile-icon '+(item.kind==='folder'?'folder-tile-icon':'')} onClick={()=>open(item)} role="button" tabIndex={0} aria-label={'Abrir '+item.name} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open(item)}}}><CloudThumbnail item={item}/></div><button className="tile-name" onClick={()=>open(item)}>{item.name}</button>{!!item.starred&&<Star className="cloud-star-mark" size={15} fill="#e2c16f" color="#e2c16f"/>}<small>{item.kind==='folder'?'Pasta':size(item.size)}</small></article>)}</div></>:<div className="table-scroll"><div className="table cloud-table"><div className="table-head"><span><input type="checkbox" checked={selected.length===visible.length&&visible.length>0} onChange={e=>setSelected(e.target.checked?visible.map(i=>i.id):[])}/> Nome</span><span>Modificado</span><span>Tamanho</span><span>Ações</span></div>{visible.map(item=><div key={item.id} className={'table-row '+(selected.includes(item.id)?'selected':'')}><div className="filename"><input type="checkbox" checked={selected.includes(item.id)} onChange={()=>toggle(item.id)}/><button onClick={()=>open(item)}><span className="cloud-row-thumb"><CloudThumbnail compact item={item}/></span><span>{item.name}</span></button></div><span>{date(item.created)}</span><span>{item.kind==='folder'?'—':size(item.size)}</span><div className="inline-actions"><button title={item.kind==='folder'?'Baixar pasta como ZIP':'Baixar'} onClick={()=>download(item)}><Download size={16}/></button>{!trash&&<button title="Compartilhar" onClick={()=>action('share',[item])}><Users size={17}/></button>}<button title={item.starred?'Remover dos favoritos':'Adicionar aos favoritos'} aria-label={'Favoritar '+item.name} onClick={()=>action('favorite',[item])}><Star size={17} fill={item.starred?'#e2c16f':'none'}/></button><button title="Renomear" aria-label={'Renomear '+item.name} onClick={()=>action('rename',[item])}><Pencil size={17}/></button><button title="Mover para outra pasta" aria-label={'Mover '+item.name} onClick={()=>action('move',[item])}><MoveRight size={18}/></button>{trash?<><button title="Restaurar" onClick={()=>action('restore',[item])}><RotateCcw size={16}/></button><button className="danger-action" title="Excluir definitivamente" onClick={()=>action('permanent',[item])}><Trash2 size={16}/></button></>:<button className="danger-action" title="Mover para lixeira" onClick={()=>action('trash',[item])}><Trash2 size={16}/></button>}</div></div>)}</div></div>}
{drag&&<div className="drop-zone" onDragLeave={e=>{if(e.currentTarget===e.target)setDrag(false)}}><Upload size={40}/><strong>Solte para enviar ao Meu Drive</strong><span>Os arquivos serão armazenados no Telegram</span></div>}
{jobs.length>0&&trayVisible&&<div className={'upload-tray '+(!panel?'upload-tray-collapsed':'')} role="region" aria-label="Gerenciador de uploads">
<div className="upload-head"><div className="upload-title"><span className="upload-title-icon"><Upload size={19}/></span><div><b>Transferências</b><small>{uploadingNow?uploadingNow+' em andamento':failures?failures+' com falha':completed+' concluído(s)'}</small></div></div><div className="upload-head-actions">{busy&&<button className="upload-cancel-all" onClick={stopUploads}>Cancelar envios</button>}<button className="upload-icon-button" title={panel?'Recolher transferências':'Expandir transferências'} aria-label={panel?'Recolher transferências':'Expandir transferências'} onClick={()=>setPanel(v=>!v)}>{panel?<ChevronDown size={18}/>:<ChevronDown size={18} style={{transform:'rotate(180deg)'}}/>}</button><button className="upload-icon-button" title="Fechar janela de transferências" aria-label="Fechar janela de transferências" onClick={()=>setTrayVisible(false)}><X size={19}/></button></div></div>
{panel&&<><div className="upload-overview"><span>{completed} de {jobs.length} concluído(s)</span><span>{Math.round(jobs.reduce((sum,j)=>sum+(j.status==='completed'?100:j.progress||0),0)/Math.max(1,jobs.length))}% transferido*</span></div>
<div className="upload-total-meter"><span style={{width:(jobs.reduce((sum,j)=>sum+(j.status==='completed'?100:j.progress||0),0)/Math.max(1,jobs.length))+'%'}}/></div>
<div className="upload-tabs">{[['all','Todos'],['pending','Em andamento'],['completed','Concluídos'],['failed','Falhas']].map(([id,label])=><button key={id} className={tab===id?'active':''} onClick={()=>setTab(id)}>{label}{id==='failed'&&failures>0?' ('+failures+')':''}</button>)}</div>
<div className="upload-items">{filteredJobs.length?filteredJobs.map(job=><div className="upload-job" key={job.id}><span className={'upload-job-icon '+job.status}>{job.status==='completed'?<Check size={17}/>:job.status==='failed'?<CircleAlert size={17}/>:job.status==='cancelled'?<X size={17}/>:<Upload size={17}/>}</span><div className="upload-job-main"><div className="upload-job-top"><span title={job.name}>{job.name}</span><small>{size(job.file.size)}</small></div><div className="upload-job-status"><span className={'upload-status-label '+job.status}>{job.status==='queued'?'Na fila':job.status==='uploading'?'Enviando':job.status==='completed'?'Concluído':job.status==='cancelled'?'Cancelado':'Falhou'}</span><span>{job.status==='uploading'?job.progress+'%':job.status==='completed'?'100%':''}</span></div><div className="upload-meter"><span style={{width:(job.status==='completed'?100:job.progress)+'%'}}/></div><small className="upload-detail">{job.detail||'Aguardando envio'}</small></div></div>):<div className="upload-empty-filter">Nenhuma transferência nesta categoria.</div>}</div>
<div className="upload-foot"><span>*Progresso do navegador até o backend; o Telegram confirma ao final.</span>{!busy&&<button onClick={()=>{setJobs([]);setTrayVisible(false)}}>Limpar histórico</button>}</div></>}</div>}
{zipProgress&&<div className="zip-progress-tray" role="status" aria-live="polite"><span className="zip-progress-icon"><FileArchive size={20}/></span><div className="zip-progress-text"><strong>Preparando pasta em ZIP</strong><small title={zipProgress.name}>{zipProgress.name}</small><div className="zip-progress-track"><span style={{width:(zipProgress.state==='ready'?100:Math.min(95,Math.round(95*(zipProgress.processed_bytes||0)/Math.max(1,zipProgress.total_bytes||1))))+'%'}}/></div><small>{zipProgress.phase==='compressing'?'Compactando arquivos...':'Baixando arquivos do Telegram...'} {zipProgress.processed_bytes||0?size(zipProgress.processed_bytes):'0 B'} de {size(zipProgress.total_bytes||0)} • {zipProgress.done||0}/{zipProgress.count||0} itens</small></div></div>}
{deleteConfirm&&<div className="dc-confirm-backdrop" role="presentation" onClick={()=>!busy&&setDeleteConfirm(null)}><div className="dc-confirm-dialog" role="alertdialog" aria-modal="true" aria-label="Confirmar exclusão" onClick={e=>e.stopPropagation()}><span className="dc-confirm-icon"><CircleAlert size={65} strokeWidth={1.9}/></span><h3>{deleteConfirm.kind==='permanent'?'Excluir definitivamente?':'Mover para a lixeira?'}</h3><div className={deleteConfirm.kind==='permanent'?'dc-confirm-warning':'dc-confirm-note'}><CircleAlert size={17}/><p>{deleteConfirm.kind==='permanent'?`Esta ação não pode ser desfeita. ${deleteConfirm.targets.length} item(ns) serão apagados do Telegram, incluindo arquivos dentro das pastas.`:`${deleteConfirm.targets.length} item(ns) serão movidos para a lixeira e poderão ser restaurados depois.`}</p></div><div className="dc-confirm-buttons"><button disabled={busy} onClick={()=>setDeleteConfirm(null)}>Cancelar</button><button className="dc-confirm-danger" disabled={busy} onClick={confirmDeletion}>{busy?'Excluindo...':deleteConfirm.kind==='permanent'?'Excluir para sempre':'Mover para lixeira'}</button></div></div></div>}
{folderDialog&&<div className="move-backdrop" role="presentation" onClick={()=>{if(!folderBusy)setFolderDialog(false)}}><div className="move-dialog folder-create-dialog" role="dialog" aria-modal="true" aria-labelledby="new-folder-title" onClick={e=>e.stopPropagation()}>
<div className="move-dialog-header"><div><h3 id="new-folder-title">Nova pasta</h3><p>Organize seus arquivos no Meu Drive.</p></div><button className="move-close" aria-label="Fechar" disabled={folderBusy} onClick={()=>setFolderDialog(false)}><X size={19}/></button></div>
<form onSubmit={e=>{e.preventDefault();submitNewFolder()}}>
<div className="folder-create-body"><label htmlFor="drive-folder-name">Nome da pasta</label><input id="drive-folder-name" autoFocus maxLength={180} value={folderName} onChange={e=>setFolderName(e.target.value)} placeholder="Digite um nome para a pasta"/><span>Ela será criada {folder?'dentro da pasta atual':'na raiz do Meu Drive'}.</span></div>
<div className="move-footer"><button type="button" disabled={folderBusy} onClick={()=>setFolderDialog(false)}>Cancelar</button><button className="move-confirm" type="submit" disabled={folderBusy||!folderName.trim()}>{folderBusy?'Criando...':'Criar pasta'}</button></div>
</form></div></div>}
{shareItem&&<ShareDialog item={shareItem} onClose={()=>setShareItem(null)} onToast={onToast}/>}
{catalogCheck&&<div className="move-backdrop" role="presentation" onClick={()=>!catalogBusy&&setCatalogCheck(null)}><div className="move-dialog" role="dialog" aria-modal="true" aria-label="Restaurar catálogo de arquivos" onClick={e=>e.stopPropagation()}><div className="move-dialog-header"><div><h3>Restaurar catálogo</h3><p title={catalogCheck.file.name}>{catalogCheck.file.name}</p></div><button className="move-close" title="Fechar" disabled={catalogBusy} onClick={()=>setCatalogCheck(null)}><X size={19}/></button></div><div className="catalog-review"><div><strong>{catalogCheck.result.checked}</strong><span>Registros verificados</span></div><div><strong>{catalogCheck.result.new_items}</strong><span>Para recuperar</span></div><div><strong>{catalogCheck.result.existing_items}</strong><span>Já existentes</span></div></div><p className="catalog-notice">A conta e o canal Telegram foram conferidos. Somente registros ausentes serão adicionados ao catálogo local. Esta operação não recupera arquivos excluídos do Telegram e não sobrescreve registros atuais.</p><div className="move-footer"><button disabled={catalogBusy} onClick={()=>setCatalogCheck(null)}>Cancelar</button><button className="move-confirm" disabled={catalogBusy||!catalogCheck.result.new_items} onClick={restoreCatalog}><DatabaseBackup size={16}/>{catalogBusy?'Restaurando...':'Restaurar registros'}</button></div></div></div>}
{moveTargets&&<div className="move-backdrop" role="presentation" onClick={()=>{if(!busy)setMoveTargets(null)}}>
<div className="move-dialog file-manager-dialog" role="dialog" aria-modal="true" aria-labelledby="move-manager-title" onClick={e=>e.stopPropagation()}>
<div className="move-dialog-header">
<div><h3 id="move-manager-title">Mover para</h3><p>{moveTargets.length===1?moveTargets[0].name:moveTargets.length+' itens selecionados'}</p></div>
<button className="move-close" title="Fechar" aria-label="Fechar" disabled={busy} onClick={()=>setMoveTargets(null)}><X size={19}/></button>
</div>
<div className="move-browser-top">
<button className="move-up" title="Voltar à pasta anterior" aria-label="Voltar à pasta anterior" disabled={!moveDestination||busy} onClick={goMoveParent}><ArrowLeft size={18}/></button>
<div className="move-path" aria-label="Caminho da pasta">
<button onClick={()=>{setMoveDestination('');setMoveNewFolder(false)}} title="Meu Drive">Meu Drive</button>
{moveBreadcrumbs.map(p=><React.Fragment key={p.id}><ChevronRight size={14}/><button onClick={()=>{setMoveDestination(p.id);setMoveNewFolder(false)}} title={p.name}>{p.name}</button></React.Fragment>)}
</div>
<button className="move-create" title="Criar nova pasta neste local" onClick={()=>setMoveNewFolder(v=>!v)} disabled={busy}><FolderPlus size={17}/> Nova pasta</button>
</div>
{moveNewFolder&&<form className="move-new-folder" onSubmit={e=>{e.preventDefault();createMoveFolder()}}>
<FolderPlus size={17}/><input autoFocus value={moveFolderName} onChange={e=>setMoveFolderName(e.target.value)} placeholder="Nome da nova pasta" maxLength={180} aria-label="Nome da nova pasta"/>
<button type="button" aria-label="Cancelar criação de pasta" onClick={()=>{setMoveNewFolder(false);setMoveFolderName('')}}><X size={16}/></button>
<button type="submit" disabled={busy||!moveFolderName.trim()}>Criar</button>
</form>}
<div className="move-browser-list" aria-label="Pastas disponíveis">
{availableMoveFolders.length?availableMoveFolders.map(item=><button key={item.id} className="move-folder-row" onClick={()=>{setMoveDestination(item.id);setMoveNewFolder(false)}} onDoubleClick={()=>setMoveDestination(item.id)} title={'Abrir '+item.name}>
<span className="move-folder-symbol"><Folder size={20} fill="#80aef2" color="#b5d1fb" strokeWidth={1.4}/></span><span className="move-folder-name">{item.name}</span><ChevronRight size={17}/></button>):<div className="move-empty"><Folder size={29}/><strong>Nenhuma subpasta aqui</strong><span>Crie uma pasta ou mova os arquivos para este local.</span></div>}
</div>
<div className="move-destination"><span>Destino selecionado</span><strong title={moveBreadcrumbs.length?moveBreadcrumbs.map(x=>x.name).join(' / '):'Meu Drive'}>{moveBreadcrumbs.length?moveBreadcrumbs.map(x=>x.name).join(' / '):'Meu Drive (raiz)'}</strong></div>
<div className="move-footer"><button type="button" disabled={busy} onClick={()=>setMoveTargets(null)}>Cancelar</button><button type="button" className="move-confirm" disabled={busy||moveNewFolder} onClick={confirmMove}>{busy?'Movendo...':'Mover aqui'}</button></div>
</div></div>}
{preview&&<div className="preview-backdrop" onClick={()=>setPreview(null)} role="presentation"><div className="preview-modal" role="dialog" aria-modal="true" aria-label={'Prévia de '+preview.name} onClick={e=>e.stopPropagation()}>
<div className="preview-topbar"><div>{isCloudVideo(preview)?<Play size={19}/>:<Image size={19}/>}<strong title={preview.name}>{preview.name}</strong><span>{size(preview.size)}</span></div><div className="preview-top-actions"><button onClick={()=>download(preview)}><Download size={16}/> Baixar</button><button title="Fechar prévia" aria-label="Fechar prévia" onClick={()=>setPreview(null)}><X size={20}/></button></div></div>
<div className="preview-stage">{previewError?<div className="preview-failed"><CircleAlert size={43}/><p>Não foi possível abrir a prévia.</p><button onClick={()=>download(preview)}>Baixar arquivo original</button></div>:isCloudVideo(preview)?<SharedMediaDisplay key={preview.id} src={'http://127.0.0.1:8000/api/cloud/media/'+encodeURIComponent(preview.id)} statusUrl={'http://127.0.0.1:8000/api/cloud/media-status/'+encodeURIComponent(preview.id)} name={preview.name} video/>:<img key={preview.id} src={'http://127.0.0.1:8000/api/cloud/preview/'+encodeURIComponent(preview.id)+'?full=true'} alt={preview.name} onError={()=>setPreviewError(true)}/>}</div>
<div className="preview-foot">{isCloudVideo(preview)?'Player Drive Cloud • Original preservado no Telegram':'Pré-visualização otimizada • JXL convertido apenas na prévia • Original preservado no Telegram'}</div></div></div>}
<p className="cloud-disclaimer">Arquivos são armazenados no canal privado; pastas e referências ficam no SQLite deste computador. Nesta versão experimental o limite é de 20 MB por arquivo e não há criptografia própria ou recuperação automática do catálogo. Não use como cópia única de backups.</p>
</section>
}
function BackupPages({section,onToast}){
 const [status,setStatus]=useState(null),[history,setHistory]=useState([]),[loading,setLoading]=useState(false),[frequency,setFrequency]=useState('off'),[error,setError]=useState('');
 const base='http://127.0.0.1:8000/api/backup';
 async function req(path,method='GET',body){
  const r=await fetch(base+path,{method,...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
  const data=await r.json();if(!r.ok)throw Error(data.detail||'Falha ao acessar backups');return data;
 }
 async function refresh(){try{const [a,b]=await Promise.all([req('/status'),req('/history')]);setStatus(a);setFrequency(a.frequency);setHistory(b.items||[]);setError('')}catch(e){setError(e.message)}}
 useEffect(()=>{refresh()},[]);
 async function snapshot(){setLoading(true);try{const result=await req('/run','POST');await refresh();onToast?.({kind:'success',message:'Catálogo salvo: '+result.item_count+' registros.'})}catch(e){setError(e.message)}finally{setLoading(false)}}
 async function schedule(value){setLoading(true);try{await req('/schedule','POST',{frequency:value});await refresh();onToast?.({kind:'success',message:value==='off'?'Agendamento desativado':'Agendamento de catálogo salvo'})}catch(e){setError(e.message)}finally{setLoading(false)}}
 return <div className="dc-module-page"><div className="dc-module-note"><DatabaseBackup size={19}/><div><strong>Backup do catálogo</strong><p>Estas cópias guardam a organização, as pastas e as referências aos arquivos do Telegram. Não são cópias dos arquivos. Para guardar arquivos offline, baixe as pastas em ZIP.</p></div></div>
 {error&&<div className="public-share-error">{error}</div>}
 {section==='backups'&&<div className="dc-dashboard-grid"><div className="dc-module-card"><div className="dc-module-card-top"><DatabaseBackup size={20}/><span>Último backup</span></div><strong>{status?.last_backup?new Date(status.last_backup.created*1000).toLocaleString('pt-BR'):'Nenhum backup ainda'}</strong><small>{status?.last_backup?status.last_backup.item_count+' registros protegidos':'Crie o primeiro snapshot local do catálogo.'}</small></div><div className="dc-module-card"><div className="dc-module-card-top"><Clock3 size={20}/><span>Agendamento</span></div><strong>{frequency==='daily'?'Diário':frequency==='weekly'?'Semanal':'Desativado'}</strong><small>{status?.next_run?'Próxima execução: '+new Date(status.next_run*1000).toLocaleString('pt-BR'):'Executa enquanto o backend local estiver ligado.'}</small></div><div className="dc-module-card"><div className="dc-module-card-top"><List size={20}/><span>Histórico</span></div><strong>{history.length} snapshots</strong><small>Últimas cópias do catálogo neste computador.</small></div></div>}
 {(section==='backups'||section==='backupSchedule')&&<div className="dc-module-section"><div><h3>Backup do catálogo</h3><p>Faça uma cópia agora ou programe snapshots automáticos.</p></div><button className="dc-module-primary" disabled={loading} onClick={snapshot}><DatabaseBackup size={17}/>{loading?'Processando...':'Criar backup agora'}</button><div className="dc-schedule-controls"><label htmlFor="backup-frequency">Frequência</label><select className="dc-native-select" id="backup-frequency" disabled={loading||!status} value={frequency} onChange={e=>schedule(e.target.value)}><option value="off">Desativado</option><option value="daily">Diariamente</option><option value="weekly">Semanalmente</option></select><small>O computador e o backend precisam permanecer ligados para executar no horário programado.</small></div></div>}
 {(section==='backups'||section==='backupHistory')&&<div className="dc-module-section"><div><h3>Histórico de backups</h3><p>Baixe o JSON para guardar uma cópia fora do computador.</p></div><div className="dc-history-list">{history.length?history.map(x=><div className="dc-history-row" key={x.id}><DatabaseBackup size={19}/><div><strong>{new Date(x.created*1000).toLocaleString('pt-BR')}</strong><small>{x.item_count} registros • {size(x.bytes)} • {x.source==='scheduled'?'Automático':'Manual'}</small></div><a href={base+'/history/'+encodeURIComponent(x.id)+'/download'} title="Baixar snapshot"><Download size={17}/> Baixar</a></div>):<p className="dc-empty-message">Ainda não existem cópias do catálogo.</p>}</div></div>}</div>
}
function SyncPages({section}){
 const [lastSeen,setLastSeen]=useState('');
 useEffect(()=>{setLastSeen(new Date().toLocaleString('pt-BR'))},[]);
 return <div className="dc-module-page"><div className="dc-module-note"><RefreshCw size={20}/><div><strong>Sincronização entre dispositivos</strong><p>O Drive Cloud usa o Telegram como armazenamento, mas a sincronização automática entre computadores e celulares ainda exige um agente local e um catálogo sincronizado seguro. Não há sincronização automática ativa nesta versão.</p></div></div>
 <div className="dc-dashboard-grid"><div className="dc-module-card"><div className="dc-module-card-top"><HardDrive size={20}/><span>Este dispositivo</span></div><strong>Computador local</strong><small>Interface aberta em {lastSeen||'agora'}</small></div><div className="dc-module-card"><div className="dc-module-card-top"><RefreshCw size={20}/><span>Sincronização</span></div><strong>Não configurada</strong><small>Nenhuma pasta do sistema está sendo sincronizada automaticamente.</small></div></div>
 <div className="dc-module-section"><h3>{section==='devices'?'Dispositivos':section==='syncActivity'?'Atividades':'Pastas sincronizadas'}</h3><p>{section==='devices'?'Somente o dispositivo local está disponível nesta fase. Nenhum outro aparelho foi autorizado para sincronização.':section==='syncActivity'?'Não existem execuções de sincronização automática para apresentar.':'Na próxima fase, um aplicativo/agente Linux poderá selecionar pastas locais, detectar mudanças e enviar versões dos arquivos ao Drive.'}</p><div className="dc-plan-steps"><span><Check size={16}/> Armazenamento Telegram conectado ao Meu Drive</span><span><Clock3 size={16}/> Próximo: agente local de sincronização</span><span><Clock3 size={16}/> Depois: dispositivos adicionais e histórico de versões</span></div></div></div>
}
function SettingsPages({section,onToast}){
 const [compact,setCompact]=useState(()=>localStorage.getItem('dc-compact')==='true');
 const [preferredLayout,setPreferredLayout]=useState(readDriveLayout);
 const [motion,setMotion]=useState(()=>localStorage.getItem('dc-reduce-motion')==='true');
 const [links,setLinks]=useState([]),[error,setError]=useState('');
 useEffect(()=>{document.documentElement.classList.toggle('dc-compact-ui',compact);document.documentElement.classList.toggle('dc-less-motion',motion)},[]);
 async function refresh(){try{const res=await fetch('http://127.0.0.1:8000/api/share');if(res.ok)setLinks((await res.json()).links||[])}catch{}}
 useEffect(()=>{refresh()},[]);
 function changeCompact(value){setCompact(value);localStorage.setItem('dc-compact',String(value));document.documentElement.classList.toggle('dc-compact-ui',value);onToast?.({kind:'success',message:'Densidade visual atualizada.'})}
 function changePreferredLayout(value){setPreferredLayout(value);localStorage.setItem('dc-file-layout',value);window.dispatchEvent(new CustomEvent('drive-layout-updated',{detail:value}));onToast?.({kind:'success',message:'Visualização padrão atualizada.'})}
 function changeMotion(value){setMotion(value);localStorage.setItem('dc-reduce-motion',String(value));document.documentElement.classList.toggle('dc-less-motion',value);onToast?.({kind:'success',message:'Preferência de animação atualizada.'})}
 async function revoke(id){try{const r=await fetch('http://127.0.0.1:8000/api/share/'+id,{method:'DELETE'});if(!r.ok)throw Error('Falha ao revogar link');await refresh();onToast?.({kind:'success',message:'Compartilhamento revogado.'})}catch(e){setError(e.message)}}
 return <div className="dc-module-page">
 {section==='settings'&&<div className="dc-dashboard-grid"><div className="dc-module-card"><div className="dc-module-card-top"><Cloud size={20}/><span>Armazenamento</span></div><strong>Telegram privado</strong><small>Controle de conexão e canal no menu Conexão Telegram.</small></div><div className="dc-module-card"><div className="dc-module-card-top"><DatabaseBackup size={20}/><span>Backups</span></div><strong>Snapshots locais</strong><small>Configure cópias de segurança do catálogo em Backups.</small></div><div className="dc-module-card"><div className="dc-module-card-top"><Users size={20}/><span>Compartilhamentos</span></div><strong>{links.filter(x=>!x.revoked&&x.expires>Date.now()/1000).length} links ativos</strong><small>Revogue links antes de compartilhar novamente.</small></div></div>}
 {(section==='settings'||section==='preferences')&&<div className="dc-module-section"><h3>Aparência</h3><p>Preferências salvas somente neste navegador.</p><div className="dc-option-row"><span><strong>Visualização de arquivos</strong><small>Modo padrão ao abrir o Meu Drive.</small></span><div className="dc-select-wrap"><select aria-label="Visualização padrão" value={preferredLayout} onChange={e=>changePreferredLayout(e.target.value)}><option value="list">Lista</option><option value="grid">Grade</option></select><ChevronDown size={15}/></div></div><label className="dc-option-row"><span><strong>Interface compacta</strong><small>Reduz espaçamentos das listas e ferramentas.</small></span><input type="checkbox" checked={compact} onChange={e=>changeCompact(e.target.checked)}/></label><label className="dc-option-row"><span><strong>Reduzir animações</strong><small>Transições mais discretas para navegação e modais.</small></span><input type="checkbox" checked={motion} onChange={e=>changeMotion(e.target.checked)}/></label></div>}
 {(section==='settings'||section==='security')&&<div className="dc-module-section"><h3>Segurança e compartilhamentos</h3><p>O backend de teste aceita somente conexões locais. Nunca exponha os arquivos de sessão ou a API administrativa na internet.</p>{error&&<p className="public-share-error">{error}</p>}<div className="dc-history-list">{links.filter(x=>!x.revoked&&x.expires>Date.now()/1000).map(x=><div className="dc-history-row" key={x.id}><Users size={18}/><div><strong>{x.name||'Item indisponível'}</strong><small>{x.mode==='download'?'Download':'Compartilhado'} • expira em {new Date(x.expires*1000).toLocaleString('pt-BR')}</small></div><button onClick={()=>revoke(x.id)}>Revogar</button></div>)}{!links.some(x=>!x.revoked&&x.expires>Date.now()/1000)&&<p className="dc-empty-message">Nenhum compartilhamento ativo.</p>}</div></div>}</div>
}
function DriveFolderTree({nodes,current,onOpen}){
 const [expanded,setExpanded]=useState({});
 useEffect(()=>{
  if(!current)return;
  const toExpand={};
  let cursor=current;
  for(let depth=0;cursor&&depth<40;depth++){
   toExpand[cursor]=true;
   cursor=nodes.find(x=>x.id===cursor)?.parent;
  }
  setExpanded(previous=>({...previous,...toExpand}));
 },[current,nodes]);
 const folders=nodes.filter(x=>x.kind==='folder'&&!x.trashed);
 function branch(parent,depth){
  if(depth>22)return null;
  return folders.filter(x=>(x.parent||null)===parent).sort((a,b)=>a.name.localeCompare(b.name,'pt-BR')).map(item=>{
   const children=folders.some(x=>x.parent===item.id);
   const open=!!expanded[item.id];
   return <div key={item.id} className="dc-tree-branch">
    <div className={'dc-tree-row '+(current===item.id?'active':'')} style={{paddingLeft:(8+depth*14)+'px'}}>
     <button className="dc-tree-expand" title={children?(open?'Recolher pasta':'Expandir pasta'):'Sem subpastas'} disabled={!children} onClick={()=>setExpanded(prev=>({...prev,[item.id]:!prev[item.id]}))}>{children?(open?<ChevronDown size={14}/>:<ChevronRight size={14}/>):<span/>}</button>
     <button className="dc-tree-name" title={item.name} onClick={()=>{onOpen(item.id);setExpanded(prev=>({...prev,[item.id]:true}))}}><Folder size={16}/><span>{item.name}</span></button>
    </div>
    {children&&<div className={'dc-tree-children '+(open?'expanded':'')}><div className="dc-tree-children-inner">{branch(item.id,depth+1)}</div></div>}
   </div>
  })
 }
 return <div className="dc-folder-tree"><div className="dc-folder-tree-heading">Pastas <span>{folders.length}</span></div>
 <button className={'dc-tree-root '+(current===null?'active':'')} onClick={()=>onOpen(null)}><Folder size={16}/><span>Raiz do Meu Drive</span></button>
 <div className="dc-tree-list">{branch(null,0)}</div></div>
}
const DRIVE_PAGES=new Set(['home','recent','starred','cloudFiles','trash','backups','backupHistory','backupSchedule','sync','devices','syncActivity','settings','telegram','security','preferences']);
function readDriveLocation(){
 const u=new URL(window.location.href);
 const page=u.searchParams.get('page');
 const folder=u.searchParams.get('folder');
 return {page:DRIVE_PAGES.has(page)?page:'home',
         folder:folder&&/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(folder)?folder:null};
}
function saveDriveLocation(page,folder,replace=false){
 const u=new URL(window.location.href);
 u.searchParams.set('page',DRIVE_PAGES.has(page)?page:'home');
 if(page==='cloudFiles'&&folder)u.searchParams.set('folder',folder);
 else u.searchParams.delete('folder');
 if(u.pathname+u.search+u.hash!==window.location.pathname+window.location.search+window.location.hash)
  window.history[replace?'replaceState':'pushState']({page,folder},'',u.pathname+u.search+u.hash);
}
function readDriveLayout(){return localStorage.getItem('dc-file-layout')==='grid'?'grid':'list'}
function App(){
const [initialReady,setInitialReady]=useState(false);
const initialRoute=useRef(readDriveLocation());
const driveSections=['cloudFiles','home','recent','starred','trash'];const [createFolderToken,setCreateFolderToken]=useState(0);const [cloudTree,setCloudTree]=useState([]);const [cloudFolder,setCloudFolder]=useState(null);const [folderTarget,setFolderTarget]=useState(()=>initialRoute.current.folder?{id:initialRoute.current.folder,nonce:1}:null);const [deletionProgress,setDeletionProgress]=useState(null);const [toast,setToast]=useState(null);const showToast=t=>setToast({...t,id:crypto.randomUUID()});const [telegramConnected,setTelegramConnected]=useState(false);const [driveUsage,setDriveUsage]=useState(null);const[items,setItems]=useState([]),[section,setSection]=useState(()=>initialRoute.current.page),[area,setArea]=useState(()=>({home:'home',recent:'home',starred:'home',cloudFiles:'files',trash:'trash',backups:'backups',backupHistory:'backups',backupSchedule:'backups',sync:'sync',devices:'sync',syncActivity:'sync',settings:'settings',telegram:'settings',security:'settings',preferences:'settings'})[initialRoute.current.page]||'home'),[folder,setFolder]=useState(null),[view,setView]=useState(readDriveLayout),[query,setQuery]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[mobile,setMobile]=useState(false);
const input=useRef(null);
const refresh=async()=>setItems(await all());
useEffect(()=>{refresh().catch(e=>setNotice('Falha ao abrir o armazenamento: '+e.message));
const refreshTelegram=async()=>{try{const status=await fetch('http://127.0.0.1:8000/api/telegram/status').then(r=>r.json());setTelegramConnected(!!status.connected);
if(status.connected){const response=await fetch('http://127.0.0.1:8000/api/cloud/usage');if(response.ok)setDriveUsage(await response.json())}
else setDriveUsage(null)}catch{setTelegramConnected(false);setDriveUsage(null)}};
refreshTelegram();const timer=setInterval(refreshTelegram,12000);return()=>clearInterval(timer)},[]);
function msg(t){showToast({kind:'info',message:t})}
const groupOf={home:'home',recent:'home',starred:'home',files:'files',cloudFiles:'files',photos:'files',shared:'files',trash:'trash',backups:'backups',backupHistory:'backups',backupSchedule:'backups',sync:'sync',devices:'sync',syncActivity:'sync',settings:'settings',telegram:'settings',security:'settings',preferences:'settings'};
const defaults={home:'home',files:'cloudFiles',trash:'trash',backups:'backups',sync:'sync',settings:'settings'};
const nav=(s,f=null)=>{setArea(groupOf[s]||'files');setSection(s);setFolder(f);setQuery('');setMobile(false);saveDriveLocation(s,s==='cloudFiles'?f:null);if(s==='cloudFiles')setFolderTarget({id:f,nonce:Date.now()})};
useEffect(()=>{const handler=()=>{const loc=readDriveLocation();setArea(groupOf[loc.page]||'home');setSection(loc.page);setFolderTarget({id:loc.folder,nonce:Date.now()});setQuery('')};window.addEventListener('popstate',handler);return()=>window.removeEventListener('popstate',handler)},[]);
const updateDriveFolder=id=>{setCloudFolder(id);if(initialReady&&section==='cloudFiles')saveDriveLocation('cloudFiles',id)};
useEffect(()=>{localStorage.setItem('dc-file-layout',view)},[view]);
const goArea=a=>nav(defaults[a]);
const visible=useMemo(()=>items.filter(i=>section==='trash'?i.trashed:!i.trashed).filter(i=>{if(section==='home')return i.kind==='file';if(section==='files')return i.parent===folder;if(section==='photos')return i.type?.startsWith('image/');if(section==='backups')return i.kind==='folder'&&i.name==='Backups'||i.name?.toLowerCase().includes('backup');if(section==='recent')return i.kind==='file';if(section==='starred')return i.starred;if(['sync','shared','backupHistory','backupSchedule','devices','syncActivity','settings','telegram','security','preferences'].includes(section))return false;return true}).filter(i=>i.name.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>a.kind===b.kind?a.name.localeCompare(b.name,'pt-BR'):a.kind==='folder'?-1:1),[items,section,folder,query]);
const trail=[];let f=folder;for(let k=0;f&&k<20;k++){const e=items.find(i=>i.id===f);if(!e)break;trail.unshift(e);f=e.parent}
async function folderCreate(){const name=window.prompt('Nome da nova pasta:');if(!name?.trim())return;try{await save({id:uid(),name:name.trim(),kind:'folder',parent:section==='files'?folder:null,time:Date.now(),trashed:false,starred:false});await refresh();msg('Pasta criada')}catch(e){msg('Erro: '+e.message)}}
async function upload(files){if(!files?.length)return;setBusy(true);try{for(const file of files){await save({id:uid(),name:file.name,kind:'file',type:file.type,size:file.size,parent:section==='files'?folder:null,time:Date.now(),trashed:false,starred:false},file)}await refresh();msg(files.length+' arquivo(s) salvo(s) neste navegador')}catch(e){msg('Erro no upload: '+e.message)}finally{setBusy(false);if(input.current)input.current.value=''}}
async function open(i){if(i.kind==='folder'){nav('files',i.id);return}try{const blob=await read(i.id);if(!blob)throw Error('Arquivo não encontrado');const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=i.name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),4000)}catch(e){msg(e.message)}}
const descendants=i=>{const ids=[i.id];for(let p=0;p<ids.length;p++)for(const other of items)if(other.parent===ids[p]&&!ids.includes(other.id))ids.push(other.id);return ids};
async function act(i,action){try{const ids=descendants(i);if(action==='delete'){if(!confirm('Excluir definitivamente? Esta ação não pode ser desfeita.'))return;await erase(ids)}else if(action==='trash'||action==='restore'){for(const id of ids){const e=items.find(x=>x.id===id);await save({...e,trashed:action==='trash',parent:action==='restore'&&e.parent&&items.find(x=>x.id===e.parent)?.trashed?null:e.parent})}}else await save({...i,starred:!i.starred});await refresh()}catch(e){msg('Erro: '+e.message)}}
const menus={
home:[['home','Visão geral',Home],['recent','Recentes',Clock3],['starred','Favoritos',Star]],
files:[['cloudFiles','Todos os arquivos',Folder]],
trash:[['trash','Lixeira',Trash2]],
backups:[['backups','Meus backups',DatabaseBackup],['backupSchedule','Agendamentos',Clock3],['backupHistory','Histórico',List]],
sync:[['sync','Pastas sincronizadas',RefreshCw],['devices','Dispositivos',HardDrive],['syncActivity','Atividades',Clock3]],
settings:[['settings','Visão geral',Settings],['telegram','Conexão Telegram',Cloud],['security','Segurança',Star],['preferences','Preferências',Settings]]
};
const primary=[['home','Início',Home],['files','Meu Drive',Folder],['trash','Lixeira',Trash2],['backups','Backups',DatabaseBackup],['sync','Sincronização',RefreshCw],['settings','Configurações',Settings]];
const sections=Object.values(menus).flat();
const label=sections.find(s=>s[0]===section)?.[1]||'Arquivos';
const bytes=items.filter(i=>i.kind==='file'&&!i.trashed).reduce((n,i)=>n+(i.size||0),0);
return <div className="shell"><aside className="rail"><div className="logo" title="Drive Cloud"><img src="/drive-cloud-logo.svg" alt="Drive Cloud"/></div>{primary.map(([a,name,Icon])=><button key={a} title={name} aria-label={name} className={area===a?'rail-on':''} onClick={()=>goArea(a)}><Icon size={21}/></button>)}</aside>
<aside className={'sidebar '+(mobile?'show':'')}><div className="sidebar-title">{primary.find(p=>p[0]===area)?.[1]||'Meu espaço'}<button className="mobile-x" onClick={()=>setMobile(false)}><X size={19}/></button></div><div className="links">{menus[area].map(([id,name,Icon])=><button key={id} className={section===id?'active':''} onClick={()=>nav(id)}><Icon size={18}/>{name}</button>)}</div>{area==='files'&&<DriveFolderTree nodes={cloudTree} current={cloudFolder} onOpen={id=>{nav('cloudFiles',id)}}/>}<div className="sidebar-bottom"><div className="dc-compact-storage">
<div className="dc-usage-heading"><HardDrive size={16}/><span>Armazenamento</span></div>
<div className="dc-usage-value">{driveUsage?size(driveUsage.total_bytes):'—'} <small>utilizados no Drive / <span title="O Telegram não informa uma cota de armazenamento para esta integração.">Sem cota informada</span></small></div>
<div className="dc-usage-breakdown"><span><i className="active"/> Arquivos {driveUsage?size(driveUsage.active_bytes||0):'—'}</span><span><i className="trash"/> Lixeira {driveUsage?size(driveUsage.trash_bytes||0):'—'}</span></div>
<div className="dc-usage-status"><i className={telegramConnected?'connected':'disconnected'}/>{telegramConnected?'Telegram conectado':'Telegram desconectado'}</div>
</div></div></aside>
<main><header><button className="mobile-toggle" onClick={()=>setMobile(!mobile)}>☰</button>{section==='cloudFiles'&&<button className="new" title="Criar pasta no Meu Drive" onClick={()=>{nav('cloudFiles');setCreateFolderToken(n=>n+1)}}><Plus size={18}/> Novo</button>}{['cloudFiles','home','recent','starred'].includes(section)&&<div className="search"><Search size={18}/><input placeholder="Buscar arquivos e pastas..." value={query} onChange={e=>setQuery(e.target.value)}/></div>}<span className="status"><i/> Modo local</span><span className="avatar">DC</span></header>
<div className="content"><div className="heading"><div><h1>{trail.length&&section==='files'?trail.at(-1).name:label}</h1>{!driveSections.includes(section)&&<p>{section==='telegram'?'Gerencie a conta e o canal privado usados pelo Drive.':area==='backups'?'Agendamentos e histórico de cópias do catálogo.':area==='sync'?'Gerencie as opções de sincronização entre dispositivos.':'Preferências e segurança do Drive Cloud.'}</p>}</div></div>
<div style={{display:driveSections.includes(section)?'block':'none'}}><CloudFiles mode={section==='cloudFiles'?'files':driveSections.includes(section)?section:'files'} globalSearch={query} onToast={showToast} onDeletionProgress={setDeletionProgress} createFolderToken={createFolderToken} onCatalogChange={setCloudTree} onFolderChange={updateDriveFolder} folderTarget={folderTarget} onInitialReady={()=>setInitialReady(true)}/></div>{section==='telegram'?<TelegramSettings onToast={showToast}/>:['backups','backupSchedule','backupHistory'].includes(section)?<BackupPages section={section} onToast={showToast}/>:['sync','devices','syncActivity'].includes(section)?<SyncPages section={section}/>:['settings','security','preferences'].includes(section)?<SettingsPages section={section} onToast={showToast}/>:!driveSections.includes(section)&&!['backups','backupSchedule','backupHistory','sync','devices','syncActivity','settings','security','preferences'].includes(section)?<><div className="toolbar"><div className="chips"><button onClick={()=>nav('recent')}><Clock3 size={15}/> Recentes</button><button onClick={()=>nav('starred')}><Star size={15}/> Favoritos</button></div><div className="toggle"><button aria-label="Modo grade" className={view==='grid'?'chosen':''} onClick={()=>setView('grid')}><Grid2X2 size={18}/></button><button aria-label="Modo lista" className={view==='list'?'chosen':''} onClick={()=>setView('list')}><List size={18}/></button></div></div>
{visible.length===0?<div className="empty"><Folder size={50}/><h3>Nenhum arquivo por aqui</h3><p>{['shared','sync','backupHistory','backupSchedule','devices','syncActivity','settings','telegram','security','preferences'].includes(section)?'Este recurso será adicionado em uma próxima etapa.':'Envie arquivos ou crie uma pasta para começar.'}</p></div>:view==='grid'?<div className="grid">{visible.map(i=><article key={i.id} className="tile"><button className="more" aria-label={'Opções de '+i.name} onClick={()=>{const action=window.prompt('Ação: '+(i.trashed?'restaurar, excluir':'abrir, favorito, lixeira'));if(!action)return;if(action==='abrir')open(i);else act(i,({favorito:'star',lixeira:'trash',restaurar:'restore',excluir:'delete'})[action]||action)}}><MoreHorizontal size={20}/></button><div className="tile-icon" onDoubleClick={()=>open(i)}><IconFile item={i} large/></div><button className="tile-name" onClick={()=>open(i)} title={i.name}>{i.name}</button><small>{i.kind==='folder'?'Pasta':size(i.size)} {i.starred?'★':''}</small></article>)}</div>:<div className="table-scroll"><div className="table"><div className="table-head"><span>Nome</span><span>Modificado</span><span>Tamanho</span><span>Ações</span></div>{visible.map(i=><div className="table-row" key={i.id}><button onClick={()=>open(i)}><IconFile item={i}/><span>{i.name} {i.starred?'★':''}</span></button><span>{date(i.time)}</span><span>{i.kind==='folder'?'—':size(i.size)}</span><div className="row-actions">{i.trashed?<><button title="Restaurar" onClick={()=>act(i,'restore')}>↶</button><button title="Excluir definitivamente" onClick={()=>act(i,'delete')}><Trash2 size={16}/></button></>:<><button title="Favorito" onClick={()=>act(i,'star')}><Star size={16} fill={i.starred?'#bca3f2':'none'}/></button><button title="Mover para lixeira" onClick={()=>act(i,'trash')}><Trash2 size={16}/></button></>}</div></div>)}</div></div>}
</>:null}<footer>{['cloudFiles','home','recent','starred'].includes(section)?'Arquivos no Telegram • Catálogo SQLite local • Versão experimental':'Área experimental • Mantenha outra cópia dos arquivos importantes'} <span>Drive Cloud • Versão local</span></footer></div></main><input ref={input} type="file" multiple hidden onChange={e=>upload([...e.target.files])}/><DriveToast toast={deletionProgress?null:toast} progress={deletionProgress} onDismiss={()=>setToast(null)}/>{!initialReady&&<div className="dc-initial-splash" role="status" aria-label="Carregando Drive Cloud" aria-busy="true"><DriveBrandLoader/></div>}</div>}
const params=new URLSearchParams(window.location.search);
const publicToken=params.get('share'),embedToken=params.get('embed');
createRoot(document.getElementById('root')).render(embedToken?<EmbeddedMedia token={embedToken}/>:publicToken?<PublicShareView token={publicToken}/>:<App/>);