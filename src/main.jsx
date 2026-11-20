import React,{useEffect,useMemo,useRef,useState} from 'react';
import{createRoot}from'react-dom/client';
import{createPortal}from'react-dom';
import{Play,Pause,Volume2,VolumeX,Maximize,Minimize,Cloud,Home,Folder,Image,DatabaseBackup,Clock3,Star,Users,RefreshCw,Trash2,Settings,Search,Plus,Upload,FolderPlus,Grid2X2,List,ChevronRight,HardDrive,WifiOff,FileText,FileArchive,File,Video,Download,MoreHorizontal,Code,X,ArrowLeft,Pencil,MoveRight,Eye,RotateCcw,Check,ChevronDown,CircleAlert}from'lucide-react';
import{all,save,read,erase}from'./storage';
import './style.css';
import {invoke} from '@tauri-apps/api/core';
import {openUrl} from '@tauri-apps/plugin-opener';
import {open as openNativeDialog} from '@tauri-apps/plugin-dialog';
let backendOrigin='http://127.0.0.1:8000';
const uid=()=>crypto.randomUUID();
const MAX_FILE_BYTES = 512*1024*1024;
const size=n=>n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';
const date=n=>new Date(n).toLocaleDateString('pt-BR');
function IconFile({item,large=false}){const n=large?56:26;if(item.kind==='folder')return <Folder size={n} fill="#8db8fc" color="#a8cbff" strokeWidth={1.4}/>;if(item.type?.startsWith('image/'))return <Image size={n} color="#c3a4ff"/>;if(item.type?.startsWith('video/'))return <Video size={n} color="#70caa8"/>;if(/zip|tar|gz|rar/i.test(item.name))return <FileArchive size={n} color="#e5bd78"/>;if(item.name.toLowerCase().endsWith('.pdf'))return <FileText size={n} color="#fa929e"/>;return <File size={n} color="#b8b8ce"/>}
function TelegramSettings({onToast}){
const [status,setStatus]=useState(null),[phone,setPhone]=useState(''),[code,setCode]=useState(''),[password,setPassword]=useState(''),[step,setStep]=useState('qr-choice'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[qrImage,setQrImage]=useState('');
const [storage,setStorage]=useState(null),[storageBusy,setStorageBusy]=useState(false),[storageError,setStorageError]=useState('');
const [apiId,setApiId]=useState(''),[apiHash,setApiHash]=useState(''),[savingApi,setSavingApi]=useState(false),[apiError,setApiError]=useState(''),[showApiHash,setShowApiHash]=useState(false);
const endpoint=backendOrigin;
async function call(path,data){const response=await fetch(endpoint+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},...(data!==undefined?{body:JSON.stringify(data)}:{})});const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'Falha na conexão');return result}
async function refresh(){try{const r=await call('/api/telegram/status');setStatus(r);setStep(r.connected?'connected':'qr-choice')}catch{setStatus({offline:true,connected:false})}}
useEffect(()=>{let active=true;let attempts=0;let timer;async function check(){if(!active)return;try{const result=await call('/api/telegram/status');if(!active)return;setStatus(result);setStep(result.connected?'connected':'qr-choice')}catch{if(!active)return;setStatus({offline:true,connected:false});if(++attempts<20)timer=setTimeout(check,1500)}}check();return()=>{active=false;clearTimeout(timer)}},[]);
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
async function saveTelegramApi(event){
 event.preventDefault();
 if(!/^[0-9]+$/.test(apiId.trim())||!Number.isSafeInteger(Number(apiId))||Number(apiId)<1||Number(apiId)>2147483647){setApiError('Informe o App api_id numérico que aparece em my.telegram.org (somente números).');return}
 if(!/^[a-fA-F0-9]{32}$/.test(apiHash.trim())){setApiError('O API Hash precisa conter 32 caracteres hexadecimais.');return}
 setSavingApi(true);setApiError('');
 try{
  await call('/api/telegram/credentials',{api_id:Number(apiId.trim()),api_hash:apiHash.trim()});
  setApiId('');setApiHash('');setShowApiHash(false);
  await refresh();
  onToast?.({kind:'success',message:'Credenciais Telegram salvas apenas neste dispositivo.'});
 }catch(err){setApiError(err.message)}finally{setSavingApi(false)}
}
async function perform(path,data){setBusy(true);setError('');try{const r=await call('/api/telegram/'+path,data);if(r.image){setQrImage(r.image);setStep('qr')}else if(r.step)setStep(r.step);if(r.connected){setStatus({...r,configured:true});setPassword('');setCode('');onToast?.({kind:'success',message:'Telegram conectado com sucesso'})}else if(path==='logout'||path==='disconnect'){setStorage(null);setStorageError('');setQrImage('');await refresh();onToast?.({kind:'info',message:path==='logout'?'Sessão do Telegram encerrada':'Conexão encerrada'})}}catch(e){setError(e.message);onToast?.({kind:'error',message:e.message,duration:6500})}finally{setBusy(false)}}
return <section className="telegram-panel"><div className="telegram-header"><div className="tg-header-icon"><img src="/drive-cloud-logo.svg?v=20261120b" alt=""/></div><div><h2>{step==='connected'?'Conta conectada':'Conectar Telegram'}</h2><p>{step==='connected'?'Sua conta autoriza o armazenamento privado do Drive Cloud.':'Autorize a conta pelo QR Code do Telegram.'}</p></div><span className={status?.connected?'tg-connection-tag active':'tg-connection-tag'}>{status?.connected?'Conectado':'Desconectado'}</span></div>
{status&&!status.offline&&!status.configured&&<div className="tg-api-setup">
 <div className="tg-api-alert"><CircleAlert size={20}/><div><strong>Configure seu acesso à API do Telegram</strong><p>Para conectar sua conta, crie gratuitamente suas credenciais pessoais no portal oficial do Telegram. O Drive Cloud não utiliza as credenciais do desenvolvedor.</p><button className="tg-api-open-link" type="button" onClick={async()=>{try{if(window.__TAURI_INTERNALS__)await openUrl("https://my.telegram.org/apps");else window.open("https://my.telegram.org/apps","_blank","noopener,noreferrer")}catch(e){setApiError("Não foi possível abrir o navegador: "+String(e))}}}>Abrir site oficial do Telegram ↗</button></div></div>
 <details className="tg-api-instructions"><summary>Como obter meu API ID e API Hash?</summary><ol><li>Acesse <strong>my.telegram.org</strong> e entre com o número da sua conta Telegram.</li><li>Selecione <strong>API development tools</strong>.</li><li>Se ainda não tiver um aplicativo cadastrado, preencha o nome, nome curto e demais dados solicitados e clique em <strong>Create application</strong>.</li><li>Copie <strong>App api_id</strong> e <strong>App api_hash</strong> para os campos abaixo.</li></ol><p>Não compartilhe o API Hash nem códigos de login. O Telegram pode permitir apenas um cadastro de API por número.</p></details>
 <form className="tg-api-form" onSubmit={saveTelegramApi}>
  <label htmlFor="dc-api-id">API ID</label>
  <input id="dc-api-id" type="text" inputMode="numeric" autoComplete="off" required value={apiId} onChange={event=>setApiId(event.target.value)} placeholder="Ex.: 12345678"/>
  <label htmlFor="dc-api-hash">API Hash</label>
  <div className="tg-api-hash-row"><input id="dc-api-hash" type={showApiHash?'text':'password'} autoComplete="off" spellCheck={false} required value={apiHash} onChange={event=>setApiHash(event.target.value)} placeholder="Cole seu App api_hash"/><button type="button" onClick={()=>setShowApiHash(!showApiHash)} aria-label={showApiHash?'Ocultar API Hash':'Mostrar API Hash'}>{showApiHash?'Ocultar':'Mostrar'}</button></div>
  {apiError&&<p className="tg-api-error" role="alert">{apiError}</p>}
  <button type="submit" disabled={savingApi||!apiId.trim()||!apiHash.trim()}>{savingApi?'Salvando...':'Salvar credenciais e continuar'}</button>
  <small>As credenciais ficam armazenadas localmente neste dispositivo, não são enviadas ao servidor do Drive Cloud. O API Hash é um segredo: evite compartilhá-lo.</small>
 </form>
 </div>}
{status?.offline?<div className="tg-warning">Não foi possível acessar o conector local do Drive Cloud. Feche outras janelas do aplicativo e abra novamente. Se continuar, consulte o diagnóstico de inicialização do backend.</div>:status&&!status.configured?<div className="tg-warning">Para conectar o Telegram, configure suas credenciais de API abaixo. Não é necessário iniciar Python manualmente.</div>:step==='connected'?<div className="tg-connected-card">
<div className="tg-account-line"><div className="tg-account-avatar">{(status?.name||'T').slice(0,1).toUpperCase()}{status?.connected&&<img src={backendOrigin+'/api/telegram/avatar?account='+encodeURIComponent(status.id||'')} alt="" onError={event=>{event.currentTarget.style.display='none'}}/>}</div><div><strong>{status?.name||'Telegram'}</strong><small>{status?.username?'@'+status.username:'Perfil conectado ao Drive Cloud'}</small></div><span className="tg-account-online"><Check size={15}/> Ativa</span></div>
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
 const promise=fetch(backendOrigin+'/api/cloud/preview/'+encodeURIComponent(item.id),{signal:controller.signal,cache:'force-cache'}).then(response=>{
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
function DriveImagePreview({src,name,onError}){
 const [loaded,setLoaded]=useState(false);
 return <div className="dc-preview-image-wrap" role="status" aria-label={loaded?'Imagem pronta':'Carregando prévia de '+name}>
 {!loaded&&<div className="dc-preview-loading"><span className="dc-preview-loading-orbit"><img src="/drive-cloud-logo.svg?v=20261120b" alt=""/></span><span>Carregando prévia...</span></div>}
 <img src={src} alt={name} onLoad={()=>setLoaded(true)} onError={onError} style={{opacity:loaded?1:0}}/>
 </div>;
}
function SharedMediaDisplay({src,statusUrl,name,video=false}){
 const [failure,setFailure]=useState(''),[attempt,setAttempt]=useState(0);
 async function fail(event){
  const mediaError=video?event?.currentTarget?.error:null;
  try{
   // Checking the actual playback endpoint catches HTTP 403/416/500 errors
   // that the lightweight catalog-only media-status endpoint cannot detect.
   const response=video?await fetch(src,{headers:{Range:'bytes=0-0'},cache:'no-store'}):
     await fetch(statusUrl,{cache:'no-store'});
   if(!response.ok){
    const body=await response.json().catch(()=>({}));
    setFailure(body.detail||'Falha ao carregar mídia (HTTP '+response.status+').');
   }else if(mediaError?.code===4){
    setFailure('Este vídeo utiliza um formato ou codec não compatível com este navegador.');
   }else if(mediaError?.code===3){
    setFailure('O navegador não conseguiu decodificar o vídeo. O arquivo pode estar danificado ou usar um codec incompatível.');
   }else{
    setFailure('O servidor respondeu, mas o navegador não conseguiu abrir a mídia. Verifique o formato e tente novamente.');
   }
  }catch{
   setFailure('Não foi possível conectar ao backend local. Confirme que ele está ativo e reinicie a prévia.');
  }
 }
 return <div className="dc-shared-media-view">
  {failure?<div className="dc-shared-media-error"><CircleAlert size={24}/><strong>Prévia indisponível</strong><p>{failure}</p><button type="button" onClick={()=>{setFailure('');setAttempt(x=>x+1)}}><RefreshCw size={15}/> Tentar novamente</button></div>
  :video?<DriveVideoPlayer key={attempt} src={src} name={name} onError={fail}/>
   :<DriveImagePreview key={attempt} src={src} name={name} onError={fail}/>}
 </div>
}
function SharedMediaThumb({src,video=false}){
 const [failed,setFailed]=useState(false);
 if(failed)return video?<Play size={24}/>:<Image size={24}/>;
 return video?<span className="dc-video-thumbnail"><Play size={22} fill="currentColor"/></span>:<img className="public-media-thumbnail" loading="lazy" alt="" src={src} onError={()=>setFailed(true)}/>;
}
function EmbeddedMedia({token}){
 const [data,setData]=useState(null),[error,setError]=useState('');
 const endpoint=backendOrigin+'/api/public/share/'+encodeURIComponent(token);
 useEffect(()=>{let cancelled=false;fetch(endpoint,{cache:'no-store'}).then(async r=>{const body=await r.json();if(!r.ok)throw Error(body.detail||'Mídia indisponível');return body}).then(d=>{if(!cancelled)setData(d)}).catch(e=>{if(!cancelled)setError(e.message)});return()=>{cancelled=true}},[token]);
 const video=data&&/\.(mp4|webm|m4v)$/i.test(data.name);
 const picture=data&&/\.(png|jpe?g|webp|gif|jxl|bmp|tiff?)$/i.test(data.name);
 return <div className="dc-embedded-media">{error?<div className="dc-embed-fail">{error}</div>:!data?<DriveCloudLoader size={64} label="Carregando mídia"/>:data.mode!=='embed'?<div className="dc-embed-fail">Incorporação não autorizada.</div>:data.kind!=='file'||(!video&&!picture)?<div className="dc-embed-fail">Formato não suportado.</div>:<SharedMediaDisplay src={endpoint+'/media?access='+encodeURIComponent(data.media_ticket||'')} statusUrl={endpoint+'/media-status'} name={data.name} video={video}/>}</div>
}
function describeSharedLinkFailure(error){
 const message=String(error?.message||'').toLowerCase();
 if(/expir/.test(message))return {title:'Este link expirou',description:'O prazo de acesso a este compartilhamento terminou. Peça ao proprietário que gere um novo link.',hint:'A validade é definida por quem compartilha o arquivo.',retry:false};
 if(/revog|desativ/.test(message))return {title:'Este compartilhamento foi encerrado',description:'O proprietário revogou o acesso. O arquivo pode continuar existindo, mas este endereço não permite mais abri-lo.',hint:'Solicite um novo link ao proprietário.',retry:false};
 if(/não está mais disponível|arquivo ou pasta não/.test(message))return {title:'Este arquivo não está mais disponível',description:'O conteúdo pode ter sido excluído ou movido para a lixeira pelo proprietário.',hint:'Confirme se o arquivo original ainda está disponível.',retry:false};
 if(error?.network||error?.status>=500)return {title:'Não foi possível conectar ao Drive Cloud',description:'Não conseguimos carregar o compartilhamento. Verifique se o Drive Cloud e seu backend estão em funcionamento.',hint:'Confira a conexão e tente novamente.',retry:true};
 if(error?.status===403)return {title:'Você não tem acesso a este conteúdo',description:'O compartilhamento não permite acesso com esta autorização.',hint:'Peça permissão ao proprietário do arquivo.',retry:false};
 if(error?.status===413)return {title:'Esta pasta não pode ser exibida',description:'O compartilhamento excedeu o limite de itens permitido nesta versão.',hint:'Peça ao proprietário que compartilhe uma pasta menor.',retry:false};
 return {title:'Não foi possível encontrar este arquivo',description:'O endereço pode estar incorreto, incompleto ou o link pode ter sido removido.',hint:'Confira se o link foi copiado por inteiro ou solicite outro.',retry:false};
}
function SharedLinkUnavailable({error,onRetry}){
 const state=describeSharedLinkFailure(error);
 return <section className="dc-share-unavailable" role="alert" aria-labelledby="shared-error-title">
  <div className="dc-share-unavailable-art" aria-hidden="true"><span className="dc-share-unavailable-glow"/><span className="dc-share-unavailable-file"><File size={49} strokeWidth={1.25}/></span><span className="dc-share-unavailable-folder"><Folder size={94} strokeWidth={1.25}/></span><span className="dc-share-unavailable-cross"><X size={19} strokeWidth={2.3}/></span></div>
  <span className="dc-share-unavailable-caption">COMPARTILHAMENTO INDISPONÍVEL</span>
  <h1 id="shared-error-title">{state.title}</h1>
  <p className="dc-share-unavailable-description">{state.description}</p>
  <div className="dc-share-unavailable-actions"><a href="/?page=home" className="dc-share-unavailable-primary"><Home size={16}/> Ir para o Meu Drive</a>{state.retry&&<button type="button" className="dc-share-unavailable-secondary" onClick={onRetry}><RefreshCw size={16}/> Tentar novamente</button>}</div>
  <p className="dc-share-unavailable-hint"><CircleAlert size={16}/>{state.hint}</p>
 </section>;
}
function PublicShareView({token}){
 const [data,setData]=useState(null),[error,setError]=useState(null),[loading,setLoading]=useState(true),[refreshKey,setRefreshKey]=useState(0),[current,setCurrent]=useState(null),[opened,setOpened]=useState(null),[search,setSearch]=useState(''),[view,setView]=useState('list');
 const endpoint=backendOrigin+'/api/public/share/'+encodeURIComponent(token);
 useEffect(()=>{let active=true;setLoading(true);setError(null);fetch(endpoint,{cache:'no-store'}).then(async r=>{const x=await r.json().catch(()=>null);if(!r.ok){const issue=new Error(typeof x?.detail==='string'?x.detail:'Não foi possível carregar este compartilhamento.');issue.status=r.status;throw issue;}return x;}).then(x=>{if(active){setData(x);setCurrent(x.root_id||null)}}).catch(e=>{if(active){setData(null);setError({message:e.message, status:e.status||0,network:!e.status})}}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[token,refreshKey]);
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
 <header className="public-share-header"><span className="public-share-brand"><img src="/drive-cloud-logo.svg?v=20261120b" alt=""/><b>Drive Cloud</b></span>{!loading&&!error&&<span className="public-share-header-pill"><Check size={13}/> Link de acesso</span>}</header>
 <div className="public-drive-wrap">
 {loading?<div className="public-share-loading" aria-busy="true"><div className="dc-shimmer public-loading-hero"/><div className="dc-shimmer public-loading-nav"/><div className="public-loading-items">{[0,1,2,3].map(i=><div className="dc-shimmer" key={i}/>)}</div><p><DriveCloudLoader size={48} label="Abrindo compartilhamento"/> Abrindo compartilhamento...</p></div>:error?<SharedLinkUnavailable error={error} onRetry={()=>setRefreshKey(x=>x+1)}/>:data&&<>
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
 <div className="public-drive-footer"><span><Clock3 size={14}/>{Number(data.expires)>=253402300799?'Link sem prazo de expiração':'Disponível até '+new Date(data.expires*1000).toLocaleString('pt-BR')}</span><span>Compartilhamento local · O computador do proprietário precisa estar ligado</span></div>
 {opened&&<div className="public-file-overlay" role="presentation" onClick={()=>setOpened(null)}><div className="public-file-preview" role="dialog" aria-modal="true" aria-label={'Visualizar '+opened.name} onClick={e=>e.stopPropagation()}><div className="public-file-preview-top"><span title={opened.name}><File size={17}/>{opened.name}</span><div><a href={endpoint+'/file/'+encodeURIComponent(opened.id)}><Download size={17}/> Baixar</a><button aria-label="Fechar visualização" onClick={()=>setOpened(null)}><X size={19}/></button></div></div><div className="public-file-preview-content">{image(opened)?<SharedMediaDisplay src={mediaUrl(opened)} statusUrl={endpoint+'/media-status?file_id='+encodeURIComponent(opened.id)} name={opened.name}/>:video(opened)?<SharedMediaDisplay src={mediaUrl(opened)} statusUrl={endpoint+'/media-status?file_id='+encodeURIComponent(opened.id)} name={opened.name} video/>:<div className="public-file-no-preview"><File size={54}/><strong>Prévia indisponível</strong><span>Baixe o arquivo para abri-lo no seu dispositivo.</span></div>}</div></div></div>}
 </>}
 </div></main>;
}

function DriveMenuSelect({value,onChange,options,label,icon:Icon,disabled=false}){
 const [open,setOpen]=useState(false),[placement,setPlacement]=useState(null),root=useRef(null),menu=useRef(null);
 const place=()=>{const rect=root.current?.getBoundingClientRect();if(!rect)return;
  const listHeight=Math.min(224,options.length*56+10);
  const above=rect.top,below=window.innerHeight-rect.bottom;
  const upwards=below<listHeight+14&&above>below;
  setPlacement({left:rect.left,top:upwards?Math.max(8,rect.top-listHeight-5):rect.bottom+5,
   width:rect.width,maxHeight:Math.min(listHeight,upwards?Math.max(100,above-15):Math.max(100,below-15))});
 };
 useEffect(()=>{if(!open)return;place();
  const hide=e=>{if(!root.current?.contains(e.target)&&!menu.current?.contains(e.target))setOpen(false)};
  const key=e=>{if(e.key==='Escape')setOpen(false)};
  const recalc=()=>place();
  document.addEventListener('pointerdown',hide);
  document.addEventListener('keydown',key);
  window.addEventListener('scroll',recalc,true);window.addEventListener('resize',recalc);
  return()=>{document.removeEventListener('pointerdown',hide);document.removeEventListener('keydown',key);
   window.removeEventListener('scroll',recalc,true);window.removeEventListener('resize',recalc)}
 },[open,options.length]);
 const active=options.find(x=>x.value===value)||options[0];
 return <div className={'dc-menu-select'+(open?' is-open':'')} ref={root}>
  <button type="button" disabled={disabled} className="dc-menu-select-trigger" aria-label={label} aria-haspopup="listbox" aria-expanded={open} onClick={()=>setOpen(x=>!x)}>
   {Icon&&<Icon size={17}/>}<span className="dc-menu-select-caption">{active?.label}</span><ChevronDown size={17} className="dc-menu-select-arrow"/>
  </button>
  {open&&placement&&createPortal(<div ref={menu} role="listbox" aria-label={label} className="dc-menu-select-options dc-select-portal" style={placement}>
   {options.map(option=><button type="button" key={option.value} disabled={option.disabled} role="option" aria-selected={value===option.value} className={'dc-menu-select-option'+(value===option.value?' selected':'')} onClick={()=>{onChange(option.value);setOpen(false)}}>
    <span className="dc-menu-select-check">{value===option.value&&<Check size={16}/>}</span><span><strong>{option.label}</strong>{option.hint&&<small>{option.hint}</small>}</span>
   </button>)}
  </div>,document.body)}
 </div>;
}
function ShareDialog({item,onClose,onToast}){
 const [mode,setMode]=useState(item.kind==='folder'?'view':'download'),[expires,setExpires]=useState('168'),[busy,setBusy]=useState(false),[created,setCreated]=useState(null),[existing,setExisting]=useState([]),[error,setError]=useState('');
 const embeddable=item.kind==='file'&&/\.(png|jpe?g|gif|webp|mp4|webm|m4v)$/i.test(item.name);
 const modes=[{value:'view',label:'Visualizar e baixar',hint:'Abrir arquivos e navegar nas pastas'},{value:'download',label:'Somente download',hint:'Baixar o arquivo ou ZIP diretamente'},...(embeddable?[{value:'embed',label:'Integração (embed)',hint:'Incorporar mídia em outro sistema'}]:[])];
 const expiryOptions=[{value:'1',label:'1 hora'},{value:'24',label:'24 horas'},{value:'168',label:'7 dias'},{value:'0',label:'Nunca expira',hint:'Até você revogar o link manualmente'}];
 const isPermanent=t=>Number(t)>=253402300799;
 async function refreshLinks(){try{const r=await fetch(backendOrigin+'/api/share');if(!r.ok)return;const data=await r.json();setExisting((data.links||[]).filter(x=>x.item_id===item.id&&!x.revoked&&x.expires>Date.now()/1000))}catch{}}
 useEffect(()=>{refreshLinks()},[item.id]);
 async function createLink(){
  if(busy)return;
  setBusy(true);setError('');
  try{
   const response=await fetch(backendOrigin+'/api/share',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_id:item.id,mode,expires_hours:Number(expires)})});
   const result=await response.json();if(!response.ok)throw Error(result.detail||'Não foi possível criar o link.');
   const route=(mode==='embed'?'/embed/d/':item.kind==='folder'?'/folder/d/':'/file/d/');
   setCreated({...result,url:window.location.origin+route+encodeURIComponent(result.token),selectedMode:mode});
   await refreshLinks();
   onToast?.({kind:'success',message:'Link criado com sucesso.'});
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function copy(textToCopy){try{await navigator.clipboard.writeText(textToCopy);onToast?.({kind:'success',message:'Copiado para a área de transferência.'})}catch{setError('Não foi possível copiar automaticamente. Selecione e copie o conteúdo do campo.')}}
 async function revoke(id){try{const response=await fetch(backendOrigin+'/api/share/'+id,{method:'DELETE'});if(!response.ok)throw Error('Falha ao revogar.');if(created?.id===id)setCreated(null);await refreshLinks();onToast?.({kind:'success',message:'Link revogado.'})}catch(e){setError(e.message)}}
 const iframe=created?.selectedMode==='embed'?'<iframe src="'+created.url+'" width="640" height="360" loading="lazy" allow="fullscreen" style="border:0;border-radius:12px" title="Mídia compartilhada"></iframe>':'';
 return <div className="move-backdrop" role="presentation" onClick={()=>!busy&&onClose()}><section className="move-dialog share-dialog dc-share-v2" role="dialog" aria-modal="true" aria-labelledby="share-dialog-title" onClick={e=>e.stopPropagation()}>
  <header className="move-dialog-header"><div className="share-dialog-heading"><span className="share-dialog-heading-icon"><Users size={21}/></span><div><h3 id="share-dialog-title">Compartilhar {item.kind==='folder'?'pasta':'arquivo'}</h3><p>Crie um link de acesso ao conteúdo</p></div></div><button type="button" className="move-close" aria-label="Fechar" onClick={onClose}><X size={19}/></button></header>
  <div className="share-dialog-body">
   <div className="share-dialog-file"><span className="share-dialog-file-icon">{item.kind==='folder'?<Folder size={22}/>:<File size={22}/>}</span><div><strong title={item.name}>{item.name}</strong><small>{item.kind==='folder'?'Pasta compartilhada':'Arquivo compartilhado'}</small></div></div>
   <div className="dc-share-field"><label>Tipo de link</label><DriveMenuSelect label="Tipo de link" value={mode} onChange={v=>{setMode(v);setCreated(null)}} options={modes} icon={Eye}/></div>
   <div className="dc-share-field"><label>Acesso geral</label><DriveMenuSelect label="Acesso geral" value="anyone" onChange={()=>{}} options={[{value:'anyone',label:'Qualquer pessoa com o link',hint:'Acesso pelo endereço compartilhado'},{value:'restricted',label:'Restrito (em desenvolvimento)',hint:'Exige autenticação do destinatário',disabled:true}]} icon={Users}/><small className="dc-share-hint">Este link funciona somente neste computador. Acesso restrito por usuário ainda não está disponível.</small></div>
   <div className="dc-share-field"><label>O link expira em</label><DriveMenuSelect label="Validade do link" value={expires} onChange={v=>{setExpires(v);setCreated(null)}} options={expiryOptions} icon={Clock3}/><small className="dc-share-hint">{expires==='0'?'O link continuará ativo até ser revogado.':'Você poderá revogar o link antes do prazo.'}</small></div>
   {created&&<div className="share-result"><label><Check size={15}/> Link criado</label><div><input value={created.url} aria-label="Endereço do compartilhamento" readOnly onFocus={e=>e.target.select()}/><button type="button" onClick={()=>copy(created.url)}><Check size={15}/> Copiar</button></div>{iframe&&<div className="share-embed-snippet"><label>Usar este link em outro sistema</label><textarea aria-label="Código de incorporação" readOnly value={iframe} onFocus={e=>e.target.select()}/><button type="button" onClick={()=>copy(iframe)}><Code size={15}/> Copiar código</button></div>}</div>}
   {error&&<div className="public-share-error"><CircleAlert size={16}/>{error}</div>}
   {!!existing.length&&<section className="share-existing"><strong>Links ativos</strong>{existing.map(link=><div key={link.id}><span>{link.mode==='download'?'Download':link.mode==='embed'?'Integração':'Visualização'} · {isPermanent(link.expires)?'Nunca expira':'Até '+new Date(link.expires*1000).toLocaleDateString('pt-BR')}</span><button type="button" onClick={()=>revoke(link.id)}>Revogar</button></div>)}</section>}
   <div className="share-local-note"><CircleAlert size={16}/> Os links gerados funcionam somente neste computador. Para compartilhar pela internet será necessário um serviço HTTPS seguro.</div>
  </div>
  <footer className="move-footer"><button type="button" onClick={onClose}>Concluir</button><button type="button" className="move-confirm" disabled={busy} onClick={createLink}><Plus size={16}/>{busy?'Criando...':'Criar link'}</button></footer>
 </section></div>;
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
  <img src="/drive-cloud-logo.svg?v=20261120b" alt=""/>
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
function CloudFiles({mode='files',globalSearch='',onToast,onDeletionProgress,createFolderToken=0,onCatalogChange,onFolderChange,folderTarget,onInitialReady,onNavigateFolder}){
const [preview,setPreview]=useState(null),[previewError,setPreviewError]=useState(false),[trayVisible,setTrayVisible]=useState(true),[cancelRequested,setCancelRequested]=useState(false),[nodes,setNodes]=useState([]),[folder,setFolder]=useState(null),[layout,setLayout]=useState(readDriveLayout),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[selected,setSelected]=useState([]),[menu,setMenu]=useState(null),[moveTargets,setMoveTargets]=useState(null),[moveDestination,setMoveDestination]=useState(''),[moveNewFolder,setMoveNewFolder]=useState(false),[moveFolderName,setMoveFolderName]=useState(''),[folderDialog,setFolderDialog]=useState(false),[folderName,setFolderName]=useState(''),[folderBusy,setFolderBusy]=useState(false),[drag,setDrag]=useState(false),[jobs,setJobs]=useState([]),[panel,setPanel]=useState(false),[tab,setTab]=useState('all'),[deleteConfirm,setDeleteConfirm]=useState(null),[deleteJob,setDeleteJob]=useState(null),[catalogCheck,setCatalogCheck]=useState(null),[catalogBusy,setCatalogBusy]=useState(false),[zipProgress,setZipProgress]=useState(null),[shareItem,setShareItem]=useState(null);
const [pendingResumable,setPendingResumable]=useState([]);
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
const base=backendOrigin+'/api/cloud';
async function refreshPendingResumable(){
 try{
  const response=await fetch(base+'/resumable/pending',{cache:'no-store'});
  if(response.ok)setPendingResumable((await response.json()).uploads||[]);
 }catch{}
}
useEffect(()=>{refreshPendingResumable()},[]);
async function discardResumable(item){
 if(!item.discardable)return;
 if(!confirm('Descartar a parte local de '+item.name+'? Isso apaga apenas o upload incompleto deste dispositivo, sem excluir arquivos do Telegram.'))return;
 try{
  const response=await fetch(base+'/resumable/'+encodeURIComponent(item.id),{method:'DELETE'});
  if(!response.ok){const data=await response.json().catch(()=>({}));throw Error(data.detail||'Não foi possível descartar o upload')}
  await refreshPendingResumable();
  onToast?.({kind:'success',message:'Parte local descartada. Seus arquivos no Telegram foram preservados.'});
 }catch(e){onToast?.({kind:'error',message:e.message})}
}

async function request(path,options){const r=await fetch(base+path,options);if(!r.ok){let detail='Erro HTTP '+r.status;try{const e=await r.json();detail=typeof e.detail==='string'?e.detail:detail}catch{}throw Error(detail)}return r}
async function reload(){try{const r=await request('/items');setNodes((await r.json()).items);setError('')}catch(e){setError(e.message)}finally{setLoading(false)}}
useEffect(()=>{reload()},[]);
useEffect(()=>{if(!loading)onInitialReady?.()},[loading,onInitialReady]);
useEffect(()=>{if(notice){onToast?.({kind:'success',message:notice});setNotice('')}},[notice]);
useEffect(()=>{if(error){onToast?.({kind:'error',message:error,duration:6500});setError('')}},[error]);
const breadcrumb=[];let current=folder;for(let n=0;current&&n<30;n++){const item=nodes.find(i=>i.id===current&&i.kind==='folder');if(!item)break;breadcrumb.unshift(item);current=item.parent}
const uploadDestination=folder?(breadcrumb[breadcrumb.length-1]?.name||'Pasta atual'):'Meu Drive';
const queryText=globalSearch.trim().toLocaleLowerCase('pt-BR');
const visible=nodes.filter(i=>trash?!!i.trashed:!i.trashed&&(queryText?true:mode==='home'?true:mode==='recent'?i.kind==='file':mode==='starred'?!!i.starred:i.parent===folder)).filter(i=>i.name.toLocaleLowerCase('pt-BR').includes(queryText)).sort((a,b)=>mode==='home'||mode==='recent'||queryText?b.created-a.created:(a.kind===b.kind?a.name.localeCompare(b.name,'pt-BR'):a.kind==='folder'?-1:1)).slice(0,mode==='home'&&!queryText?16:undefined);
const homeRecent=nodes.filter(i=>!i.trashed&&i.kind==='file').sort((a,b)=>b.created-a.created).slice(0,5);
const homeFavorites=nodes.filter(i=>!i.trashed&&i.starred).sort((a,b)=>b.created-a.created).slice(0,5);
const chosen=visible.filter(i=>selected.includes(i.id));
const setJob=(id,values)=>setJobs(j=>j.map(x=>x.id===id?{...x,...values}:x));
async function runResumableUpload(entry){
 const file=entry.file;
 // A stable sample fingerprint binds a resumed local staging session to the
 // same filename, size, modification time and start/end bytes.
 const head=await file.slice(0,65536).arrayBuffer();
 const tail=await file.slice(Math.max(0,file.size-65536)).arrayBuffer();
 const metadata=new TextEncoder().encode([file.name,file.size,file.lastModified].join(':'));
 const sample=new Uint8Array(metadata.byteLength+head.byteLength+tail.byteLength);
 sample.set(metadata,0);
 sample.set(new Uint8Array(head),metadata.byteLength);
 sample.set(new Uint8Array(tail),metadata.byteLength+head.byteLength);
 const hex=bytes=>Array.from(new Uint8Array(bytes),n=>n.toString(16).padStart(2,'0')).join('');
 const signature=hex(await crypto.subtle.digest('SHA-256',sample));
 const key='dc-resume:'+signature+':'+(entry.parent||'root');
 let uploadId;
 try{uploadId=localStorage.getItem(key)}catch{}
 if(!uploadId)uploadId=crypto.randomUUID();
 const remember=id=>{try{localStorage.setItem(key,id)}catch{}};
 const forget=()=>{try{localStorage.removeItem(key)}catch{}};
 const json=async(response,context)=>{
  const value=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:context+' (HTTP '+response.status+')');
  return value;
 };
 const begin=async(id)=>json(await fetch(base+'/resumable/start',{
  method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({upload_id:id,name:file.name,size:file.size,
    mime:file.type||'application/octet-stream',signature,parent:entry.parent||null}),
 }),"Não foi possível iniciar a retomada");
 let state;
 try{state=await begin(uploadId)}
 catch(error){
  if(!/ID de upload pertence a outro arquivo|outro arquivo, pasta ou conta/.test(error.message))throw error;
  forget();uploadId=crypto.randomUUID();state=await begin(uploadId);
 }
 remember(uploadId);
 if(state.completed){forget();return}
 let offset=state.offset||0;
 const controller=new AbortController();
 active.current=controller;
 try{
  while(offset<file.size){
   if(cancelAll.current)throw Error('Envio pausado; escolha o mesmo arquivo novamente para retomar.');
   const slice=file.slice(offset,Math.min(file.size,offset+(state.max_chunk_size||1048576)));
   const data=await slice.arrayBuffer();
   const checksum=hex(await crypto.subtle.digest('SHA-256',data));
   const response=await fetch(base+'/resumable/'+encodeURIComponent(uploadId)+'/chunk?offset='+offset+'&checksum='+checksum,{
    method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:data,signal:controller.signal,
   });
   if(response.status===409){
    const refreshed=await json(await fetch(base+'/resumable/'+encodeURIComponent(uploadId)),'Não foi possível retomar');
    if(refreshed.offset>offset){offset=refreshed.offset;continue}
   }
   const dataResponse=await json(response,'Erro ao enviar parte');
   if(dataResponse.offset<=offset)throw Error('A parte não avançou; confira a conexão local.');
   offset=dataResponse.offset;
   setJob(entry.id,{progress:Math.round(offset/file.size*72),
    detail:'Enviando ao conector local ('+Math.round(offset/file.size*100)+'%)'});
  }
  setJob(entry.id,{progress:73,detail:'Conector completo. Enviando arquivo ao Telegram...'});
  let pollTimer;
  try{
   pollTimer=setInterval(async()=>{
    try{
     const response=await fetch(base+'/upload-progress/'+encodeURIComponent(uploadId),{cache:'no-store'});
     if(!response.ok)return;
     const p=await response.json();
     if(p.stage==='telegram'&&p.total>0){
      setJob(entry.id,{progress:Math.min(98,Math.round(73+25*p.sent/p.total)),
       detail:'Transferindo ao Telegram...'});
     }
    }catch{}
   },600);
   const result=await json(await fetch(base+'/resumable/'+encodeURIComponent(uploadId)+'/complete',{
    method:'POST',signal:controller.signal,
   }),'Falha ao confirmar envio no Telegram');
   if(!result.completed)throw Error('O envio ainda não foi confirmado.');
  }finally{if(pollTimer)clearInterval(pollTimer)}
  forget();
 }finally{if(active.current===controller)active.current=null}
}
function addFiles(inputFiles){
 const files=Array.from(inputFiles||[]);if(!files.length)return;
 const valid=files.filter(file=>file.size<=MAX_FILE_BYTES);
 const rejected=files.filter(file=>file.size>MAX_FILE_BYTES);
 if(rejected.length){
   onToast?.({kind:'error',message:rejected.length===1?'Arquivo excede o limite atual de 512 MB: '+rejected[0].name:rejected.length+' arquivos excedem o limite atual de 512 MB.',duration:6500});
 }
 if(!valid.length){
   // Validation errors show only a toast. Never open an empty transfer window.
   if(!busy)setTrayVisible(false);
   if(uploader.current)uploader.current.value='';
   return;
 }
 cancelAll.current=false;
 setCancelRequested(false);
 const entries=valid.map(file=>({id:crypto.randomUUID(),file,name:file.name,parent:folder||null,destination:uploadDestination,progress:0,status:'queued'}));
 setJobs(j=>[...j,...entries]);setTrayVisible(true);setPanel(false);
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
   if(entry.file.size>=8*1024*1024){
    await runResumableUpload(entry);
   }else await new Promise((resolve,reject)=>{
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
    if(entry.parent)body.append('parent',entry.parent);
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
   await refreshPendingResumable();
  }
 }
 setBusy(false);
 if(uploader.current)uploader.current.value='';
}
function stopUploads(){if(cancelAll.current)return;cancelAll.current=true;setCancelRequested(true);setJobs(j=>j.map(x=>x.status==='queued'?{...x,status:'cancelled'}:x));active.current?.abort()}
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
async function open(item){if(item.kind==='folder'){if(mode!=='files'){onNavigateFolder?.(item.id)}else setFolder(item.id);setSelected([]);setMenu(null)}else if(isCloudImage(item)||isCloudVideo(item)){setPreview(item);setPreviewError(false);setMenu(null)}else await download(item)}
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
// In the compact tray follow the active upload first, then the next queued
// item in insertion order. Previously the last queued file hid the active one.
const featuredJob=jobs.find(x=>x.status==='uploading')||jobs.find(x=>x.status==='queued')||jobs[jobs.length-1];
const featuredPosition=featuredJob?jobs.findIndex(x=>x.id===featuredJob.id)+1:0;
const uploadStatus=cancelRequested?(uploadingNow?'cancelling':'cancelled'):uploadingNow?'sending':failures?'failed':completed?'complete':'cancelled';
const jobIcon=job=>/\.(jpg|jpeg|png|webp|gif|jxl|avif|bmp)$/i.test(job.name)?<Image size={18}/>: /\.(mp4|m4v|mkv|mov|webm)$/i.test(job.name)?<Video size={18}/>:<File size={18}/>;
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

return <section className="cloud-page" onDragEnter={e=>{e.preventDefault();if(e.dataTransfer?.types?.includes('Files'))setDrag(true)}} onDragOver={e=>e.preventDefault()} onDragLeave={e=>{const b=e.currentTarget.getBoundingClientRect();if(e.clientX<=b.left||e.clientX>=b.right||e.clientY<=b.top||e.clientY>=b.bottom)setDrag(false)}} onDrop={e=>{e.preventDefault();setDrag(false);if(e.dataTransfer?.files?.length)addFiles(e.dataTransfer.files)}}>
{pendingResumable.length>0&&<div className="dc-resume-banner"><div className="dc-resume-heading"><RefreshCw size={17}/><strong>Uploads pendentes neste computador</strong><small>{pendingResumable.length} arquivo(s)</small></div>
 <p>Para retomar um envio pausado, selecione novamente o mesmo arquivo na mesma pasta. Arquivos com envio incerto ao Telegram não serão reenviados automaticamente.</p>
 {pendingResumable.slice(0,5).map(item=><div className="dc-resume-item" key={item.id}><span><strong title={item.name}>{item.name}</strong><small>{item.state==='staging'?Math.round(100*item.offset/Math.max(1,item.size))+'% recebido no conector':'Verificação do Telegram pendente'}</small></span>
  {item.discardable&&<button type="button" onClick={()=>discardResumable(item)}>Descartar parte local</button>}</div>)}
 <button type="button" className="dc-resume-repick" onClick={()=>uploader.current?.click()}>Escolher arquivo para retomar</button></div>}

{mode==='home'&&!queryText&&!loading&&<div className="home-sections">
<section><div className="home-section-title"><Clock3 size={17}/><h3>Recentes</h3><span>Últimos arquivos enviados</span></div><div className="home-quick-list">{homeRecent.length?homeRecent.map(item=><button key={item.id} onClick={()=>open(item)}><span className="home-quick-thumb"><CloudThumbnail item={item} compact/></span><span className="home-quick-name">{item.name}</span><small>{date(item.created)}</small></button>):<p>Seus arquivos recentes aparecerão aqui.</p>}</div></section>
<section><div className="home-section-title"><Star size={17}/><h3>Favoritos</h3><span>Acesso rápido</span></div><div className="home-quick-list">{homeFavorites.length?homeFavorites.map(item=><button key={item.id} onClick={()=>open(item)}><span className="home-quick-thumb"><CloudThumbnail item={item} compact/></span><span className="home-quick-name">{item.name}</span><Star size={15} fill="#e2c16f" color="#e2c16f"/></button>):<p>Marque arquivos com a estrela para acessá-los rapidamente.</p>}</div></section>
</div>}
<div className="cloud-toolbar"><div className="cloud-crumb"><button onClick={()=>{setFolder(null);setSelected([])}}>{mode==='home'?'Visão geral':mode==='recent'?'Recentes':mode==='starred'?'Favoritos':mode==='trash'?'Lixeira':'Meu Drive'}</button>{breadcrumb.map(p=><React.Fragment key={p.id}><ChevronRight size={14}/><button onClick={()=>{setFolder(p.id);setSelected([])}}>{p.name}</button></React.Fragment>)}</div><div className="cloud-controls">{!trash&&<><button disabled={busy} onClick={newFolder}><FolderPlus size={16}/> Nova pasta</button><button className="cloud-primary" disabled={busy} onClick={()=>uploader.current?.click()}><Upload size={16}/> Upload</button></>}{mode==='files'&&<><button title="Exportar catálogo para backup" aria-label="Exportar catálogo" onClick={exportCatalog}><DatabaseBackup size={16}/></button><button title="Restaurar catálogo exportado" aria-label="Restaurar catálogo" disabled={catalogBusy} onClick={()=>catalogPicker.current?.click()}><RotateCcw size={16}/></button></>}<button title="Atualizar" onClick={reload}><RefreshCw size={16}/></button><div className="toggle"><button title="Grade" className={layout==='grid'?'chosen':''} onClick={()=>setLayout('grid')}><Grid2X2 size={17}/></button><button title="Lista" className={layout==='list'?'chosen':''} onClick={()=>setLayout('list')}><List size={17}/></button></div></div></div>
<input type="file" multiple hidden ref={uploader} onChange={e=>addFiles(e.target.files)}/><input type="file" accept=".json,application/json" hidden ref={catalogPicker} onChange={e=>checkCatalog(e.target.files?.[0])}/>
<div className="selection-zone"><div className={'bulkbar '+(selected.length?'is-visible':'')} aria-hidden={!selected.length}><div className="bulk-actions"><button className="bulk-primary" disabled={!selected.length} onClick={()=>action('download',chosen)}><Download size={16}/> Baixar</button>{trash?<><button disabled={!selected.length} onClick={()=>action('restore',chosen)}>Restaurar</button><button className="danger-action" disabled={!selected.length} onClick={()=>action('permanent',chosen)}><Trash2 size={15}/> Excluir definitivamente</button></>:<>{selected.length===1&&<button onClick={()=>action('share',chosen)}><Users size={15}/> Compartilhar</button>}<button disabled={!selected.length} onClick={()=>action('move',chosen)}>Mover</button><button className="danger-action" disabled={!selected.length} onClick={()=>action('trash',chosen)}><Trash2 size={15}/> Excluir</button></>}<button disabled={!selected.length} onClick={()=>setSelected([])}>Limpar</button></div><strong>{selected.length} selecionado{selected.length===1?'':'s'}</strong></div></div>

{loading?<DriveLoadingSkeleton layout={layout} home={mode==='home'}/>:visible.length===0?<div className="empty"><Folder size={43}/><h3>{trash?'Lixeira vazia':mode==='starred'?'Nenhum favorito ainda':mode==='recent'?'Nenhum arquivo recente':mode==='home'?'Seu Drive está pronto':'Esta pasta está vazia'}</h3><p>{mode==='starred'?'Marque uma estrela em qualquer arquivo ou pasta para encontrá-lo aqui.':mode==='files'?'Arraste arquivos para esta janela ou clique em Upload.':'Seus arquivos armazenados no Telegram aparecerão aqui.'}</p></div>:layout==='grid'?<><div className="cloud-selectall"><label><input type="checkbox" checked={selected.length===visible.length&&visible.length>0} onChange={e=>setSelected(e.target.checked?visible.map(i=>i.id):[])}/> Selecionar tudo</label></div><div className="grid">{visible.map(item=><article key={item.id} className={'tile cloud-tile '+(selected.includes(item.id)?'selected':'')}><label className="tile-select"><input type="checkbox" checked={selected.includes(item.id)} onChange={()=>toggle(item.id)} aria-label={'Selecionar '+item.name}/></label><div className="tile-menu"><button className={'file-menu-trigger '+(menu===item.id?'is-open':'')} title="Mais opções" aria-label={'Opções '+item.name} aria-expanded={menu===item.id} onClick={()=>setMenu(menu===item.id?null:item.id)}><MoreHorizontal size={19}/></button>{menu===item.id&&<><button className="file-menu-dismiss" aria-label="Fechar menu" onClick={()=>setMenu(null)}/><div className="file-menu" role="menu"><div className="file-menu-title" title={item.name}>{item.name}</div>{<button role="menuitem" onClick={()=>action('download',[item])}><Download size={17}/> {item.kind==='folder'?'Baixar como ZIP':'Baixar'}</button>}{(isCloudImage(item)||isCloudVideo(item))&&<button role="menuitem" onClick={()=>{setPreview(item);setPreviewError(false);setMenu(null)}}><Eye size={17}/> {isCloudVideo(item)?'Reproduzir vídeo':'Visualizar imagem'}</button>}<div className="file-menu-separator"/>{!trash&&<button role="menuitem" onClick={()=>action('share',[item])}><Users size={17}/> Compartilhar link</button>}<button role="menuitem" onClick={()=>action('favorite',[item])}><Star size={17} fill={item.starred?'#e2c16f':'none'}/> {item.starred?'Remover dos favoritos':'Adicionar aos favoritos'}</button><button role="menuitem" onClick={()=>action('rename',[item])}><Pencil size={17}/> Renomear</button><button role="menuitem" onClick={()=>action('move',[item])}><MoveRight size={17}/> Mover para...</button><div className="file-menu-separator"/>{trash?<><button role="menuitem" onClick={()=>action('restore',[item])}><RotateCcw size={17}/> Restaurar</button><button role="menuitem" className="danger-action" onClick={()=>action('permanent',[item])}><Trash2 size={17}/> Excluir definitivamente</button></>:<button role="menuitem" className="danger-action" onClick={()=>action('trash',[item])}><Trash2 size={17}/> Mover para lixeira</button>}</div></>}</div><div className={'tile-icon '+(item.kind==='folder'?'folder-tile-icon':'')} onClick={()=>open(item)} role="button" tabIndex={0} aria-label={'Abrir '+item.name} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open(item)}}}><CloudThumbnail item={item}/></div><button className="tile-name" onClick={()=>open(item)}>{item.name}</button>{!!item.starred&&<Star className="cloud-star-mark" size={15} fill="#e2c16f" color="#e2c16f"/>}<small>{item.kind==='folder'?'Pasta':size(item.size)}</small></article>)}</div></>:<div className="table-scroll"><div className="table cloud-table"><div className="table-head"><span><input type="checkbox" checked={selected.length===visible.length&&visible.length>0} onChange={e=>setSelected(e.target.checked?visible.map(i=>i.id):[])}/> Nome</span><span>Modificado</span><span>Tamanho</span><span>Ações</span></div>{visible.map(item=><div key={item.id} className={'table-row '+(selected.includes(item.id)?'selected':'')}><div className="filename"><input type="checkbox" checked={selected.includes(item.id)} onChange={()=>toggle(item.id)}/><button onClick={()=>open(item)}><span className="cloud-row-thumb"><CloudThumbnail compact item={item}/></span><span>{item.name}</span></button></div><span>{date(item.created)}</span><span>{item.kind==='folder'?'—':size(item.size)}</span><div className="inline-actions"><button title={item.kind==='folder'?'Baixar pasta como ZIP':'Baixar'} onClick={()=>download(item)}><Download size={16}/></button>{!trash&&<button title="Compartilhar" onClick={()=>action('share',[item])}><Users size={17}/></button>}<button title={item.starred?'Remover dos favoritos':'Adicionar aos favoritos'} aria-label={'Favoritar '+item.name} onClick={()=>action('favorite',[item])}><Star size={17} fill={item.starred?'#e2c16f':'none'}/></button><button title="Renomear" aria-label={'Renomear '+item.name} onClick={()=>action('rename',[item])}><Pencil size={17}/></button><button title="Mover para outra pasta" aria-label={'Mover '+item.name} onClick={()=>action('move',[item])}><MoveRight size={18}/></button>{trash?<><button title="Restaurar" onClick={()=>action('restore',[item])}><RotateCcw size={16}/></button><button className="danger-action" title="Excluir definitivamente" onClick={()=>action('permanent',[item])}><Trash2 size={16}/></button></>:<button className="danger-action" title="Mover para lixeira" onClick={()=>action('trash',[item])}><Trash2 size={16}/></button>}</div></div>)}</div></div>}
{drag&&<div className="drop-zone dc-drop-v2" aria-label={'Solte arquivos para enviar à pasta '+uploadDestination}>
 <div className="dc-drop-center"><div className="dc-drop-illustration" aria-hidden="true">
  <div className="dc-drop-folder"><Folder size={105} strokeWidth={1.25}/><div className="dc-drop-image"><Image size={35} strokeWidth={1.6}/></div></div>
  <div className="dc-drop-float-arrow"><Upload size={25} strokeWidth={2.2}/></div>
 </div><h2>Solte seus arquivos aqui</h2><p>Os arquivos serão enviados para a pasta</p>
 <div className="dc-drop-target" title={uploadDestination}><Folder size={17}/><strong>{uploadDestination}</strong></div></div>
 </div>}
{jobs.length>0&&trayVisible&&<div className={'upload-tray dc-upload-v2 '+(panel?'is-expanded':'is-compact')+' dc-upload-'+uploadStatus} role="region" aria-label="Gerenciador de uploads">
 <div className="upload-head">
  <div className="upload-title">
   <div className={'dc-upload-title-visual '+uploadStatus} aria-hidden="true"><Folder size={21} strokeWidth={1.95}/></div>
   <div><b aria-live="polite">{uploadStatus==='sending'?'Fazendo upload de '+uploadingNow+' '+(uploadingNow===1?'item':'itens'):uploadStatus==='failed'?failures+' '+(failures===1?'upload com falha':'uploads com falha'):uploadStatus==='complete'?completed+(completed===1?' upload concluído':' uploads concluídos'):uploadStatus==='cancelling'?'Pausando envios...':'Transferências interrompidas'}</b>{panel&&<small>{uploadStatus==='complete'?'Arquivos salvos no Drive':uploadStatus==='sending'?'Transferindo arquivos para o Telegram':'Gerenciador de transferências'}</small>}</div>
  </div>
  <div className="upload-head-actions">{busy&&!cancelRequested&&uploadingNow>0&&<button className="upload-cancel-all" onClick={stopUploads}>Pausar envios</button>}<button type="button" className="upload-icon-button" aria-label={panel?'Recolher':'Expandir'} onClick={()=>setPanel(v=>!v)}><ChevronDown size={18} style={{transform:panel?'rotate(0deg)':'rotate(180deg)'}}/></button><button type="button" className="upload-icon-button" aria-label="Fechar transferências" onClick={()=>setTrayVisible(false)}><X size={18}/></button></div>
 </div>
 {!panel&&featuredJob&&<div className="dc-compact-upload-item">
  <span className="dc-compact-upload-icon file" aria-hidden="true">{jobIcon(featuredJob)}</span>
  <div className="dc-compact-upload-info"><strong title={featuredJob.name} aria-live="polite">{featuredJob.name}</strong>
   <small className="dc-upload-path" title={featuredJob.destination||'Meu Drive'}><Folder size={12}/>{featuredJob.status==='completed'?'Salvo em':featuredJob.status==='failed'?'Destino':featuredJob.status==='queued'?'Na fila para':'Enviando para'} <b>{featuredJob.destination||'Meu Drive'}</b>{jobs.length>1&&<span className="dc-upload-queue-position">{featuredPosition} de {jobs.length}</span>}</small>
   {['queued','uploading'].includes(featuredJob.status)&&<div className="upload-meter"><span style={{width:(featuredJob.progress||0)+'%'}}/></div>}
   {featuredJob.status==='failed'&&<small className="dc-upload-failure">{featuredJob.detail||'Falha no envio'}</small>}
  </div>
  {featuredJob.status==='completed'?null:featuredJob.status==='failed'?<CircleAlert size={18} color="#e79c9c"/>:featuredJob.status==='cancelled'?null:<span className="dc-compact-progress-label">{featuredJob.progress||0}%</span>}
 </div>}
 {panel&&<><div className="upload-overview"><span>{completed} de {jobs.length} concluído(s)</span><span>{Math.round(jobs.reduce((sum,j)=>sum+(j.status==='completed'?100:j.progress||0),0)/Math.max(1,jobs.length))}%</span></div>
 <div className="upload-total-meter"><span style={{width:(jobs.reduce((sum,j)=>sum+(j.status==='completed'?100:j.progress||0),0)/Math.max(1,jobs.length))+'%'}}/></div>
 <div className="upload-tabs">{[['all','Todos'],['pending','Em andamento'],['completed','Concluídos'],['failed','Falhas']].map(([id,label])=><button key={id} className={tab===id?'active':''} onClick={()=>setTab(id)}>{label}</button>)}</div>
 <div className="upload-items">{filteredJobs.length?filteredJobs.map(job=><div className="upload-job" key={job.id}><span className="upload-job-icon dc-file-glyph" aria-hidden="true">{jobIcon(job)}</span><div className="upload-job-main"><div className="upload-job-top"><span title={job.name}>{job.name}</span><small>{size(job.file.size)}</small></div><div className="upload-job-status"><span>{job.status==='completed'?'Concluído':job.status==='failed'?'Falhou':job.status==='queued'?'Na fila':job.status==='cancelled'?'Cancelado':'Enviando...'}</span><span>{job.progress||0}%</span></div><div className="upload-meter"><span style={{width:(job.progress||0)+'%'}}/></div><small className="upload-detail">{job.detail||'Aguardando envio'}</small><small className="dc-upload-path" title={job.destination||'Meu Drive'}><Folder size={12}/>{job.destination||'Meu Drive'}</small></div></div>):<div className="upload-empty-filter">Nenhuma transferência nesta categoria.</div>}</div>
 <div className="upload-foot"><span>{jobs.some(x=>x.file?.size>=8*1024*1024&&['failed','cancelled'].includes(x.status))?'Para retomar um arquivo grande, escolha novamente o mesmo arquivo. O envio local continuará do último bloco confirmado.':'O Telegram confirma quando o arquivo termina de subir.'}</span>{!busy&&<button type="button" onClick={()=>{setJobs([]);setTrayVisible(false)}}>Limpar</button>}</div></>}
</div>}
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
<div className="preview-stage">{previewError?<div className="preview-failed"><CircleAlert size={43}/><p>Não foi possível abrir a prévia.</p><button onClick={()=>download(preview)}>Baixar arquivo original</button></div>:isCloudVideo(preview)?<SharedMediaDisplay key={preview.id} src={backendOrigin+'/api/cloud/media/'+encodeURIComponent(preview.id)} statusUrl={backendOrigin+'/api/cloud/media-status/'+encodeURIComponent(preview.id)} name={preview.name} video/>:<DriveImagePreview key={preview.id} src={backendOrigin+'/api/cloud/preview/'+encodeURIComponent(preview.id)+'?full=true'} name={preview.name} onError={()=>setPreviewError(true)}/>}</div>
<div className="preview-foot">{isCloudVideo(preview)?'Player Drive Cloud • Original preservado no Telegram':'Pré-visualização otimizada • JXL convertido apenas na prévia • Original preservado no Telegram'}</div></div></div>}
<p className="cloud-disclaimer">Arquivos são armazenados no canal privado; pastas e referências ficam no SQLite deste computador. O limite atual é de 512 MB por arquivo; ainda não há criptografia própria nem recuperação automática de conflitos do catálogo. Não use como cópia única de backups.</p>
</section>
}
function BackupPages({section,onToast}){
 const [status,setStatus]=useState(null),[history,setHistory]=useState([]),[loading,setLoading]=useState(false),[frequency,setFrequency]=useState('off'),[error,setError]=useState('');
 const [remoteSnapshot,setRemoteSnapshot]=useState(null),[remoteBusy,setRemoteBusy]=useState(false),[remoteError,setRemoteError]=useState('');
 const [restorePreview,setRestorePreview]=useState(null);
 const base=backendOrigin+'/api/backup';
 async function req(path,method='GET',body){
  const r=await fetch(base+path,{method,...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
  const data=await r.json();if(!r.ok)throw Error(data.detail||'Falha ao acessar backups');return data;
 }
 async function refresh(){try{const [a,b]=await Promise.all([req('/status'),req('/history')]);setStatus(a);setFrequency(a.frequency);setHistory(b.items||[]);setError('')}catch(e){setError(e.message)}}
 useEffect(()=>{refresh()},[]);
 async function snapshot(){setLoading(true);try{const result=await req('/run','POST');await refresh();onToast?.({kind:'success',message:'Catálogo salvo: '+result.item_count+' registros.'})}catch(e){setError(e.message)}finally{setLoading(false)}}
 async function schedule(value){setLoading(true);try{await req('/schedule','POST',{frequency:value});await refresh();onToast?.({kind:'success',message:value==='off'?'Agendamento desativado':'Agendamento de catálogo salvo'})}catch(e){setError(e.message)}finally{setLoading(false)}}
 async function fetchRemoteInfo(){
  setRemoteBusy(true);setRemoteError('');
  try{
   const response=await fetch(backendOrigin+'/api/cloud/catalog/telegram/latest');
   if(response.status===404){setRemoteSnapshot(null);return}
   const data=await response.json();
   if(!response.ok)throw Error(data.detail||'Falha ao localizar catálogo no Telegram');
   setRemoteSnapshot(data);
  }catch(e){setRemoteError(e.message)}finally{setRemoteBusy(false)}
 }
 async function restoreFromTelegram(dryRun=true){
  setRemoteBusy(true);setRemoteError('');
  try{
   const download=await fetch(backendOrigin+'/api/cloud/catalog/telegram/download',{cache:'no-store'});
   if(!download.ok){const detail=await download.json().catch(()=>({}));throw Error(detail.detail||'Não foi possível recuperar a cópia do Telegram')}
   const blob=await download.blob();
   const form=new FormData();
   form.append('file',blob,'drive-cloud-telegram-catalog.json');
   form.append('dry_run',String(dryRun));
   const result=await fetch(backendOrigin+'/api/cloud/catalog/import',{method:'POST',body:form});
   const data=await result.json().catch(()=>({}));
   if(!result.ok)throw Error(data.detail||'Não foi possível validar os dados da cópia');
   if(dryRun){setRestorePreview(data)}
   else {setRestorePreview(null);onToast?.({kind:'success',message:data.imported+' itens recuperados. Reabra Meu Drive para atualizar a lista.'})}
  }catch(e){setRestorePreview(null);setRemoteError(e.message)}finally{setRemoteBusy(false)}
 }
 async function saveRemoteSnapshot(){
  setRemoteBusy(true);setRemoteError('');
  try{
   const response=await fetch(backendOrigin+'/api/cloud/catalog/telegram/snapshot',{method:'POST'});
   const data=await response.json();
   if(!response.ok)throw Error(data.detail||'Falha ao salvar catálogo no Telegram');
   await fetchRemoteInfo();
   onToast?.({kind:'success',message:'Cópia da organização salva no seu Telegram.'});
  }catch(e){setRemoteError(e.message)}finally{setRemoteBusy(false)}
 }
 return <div className="dc-module-page"><div className="dc-module-note"><DatabaseBackup size={19}/><div><strong>Backup do catálogo</strong><p>Estas cópias guardam a organização, as pastas e as referências aos arquivos do Telegram. Não são cópias dos arquivos. Para guardar arquivos offline, baixe as pastas em ZIP.</p></div></div>
 {error&&<div className="public-share-error">{error}</div>}
 {(section==='backups'||section==='backupHistory')&&<div className="dc-module-section"><div><h3>Catálogo no Telegram</h3><p>Salve no seu canal privado uma cópia da organização das pastas e das referências dos arquivos. Esta cópia não substitui arquivos locais nem ativa sincronização automática.</p></div>
 <div className="dc-schedule-controls"><button className="dc-module-primary" disabled={remoteBusy} onClick={saveRemoteSnapshot}><DatabaseBackup size={17}/>{remoteBusy?'Aguarde...':'Salvar catálogo no Telegram'}</button><button disabled={remoteBusy} onClick={fetchRemoteInfo}>Verificar cópia no Telegram</button><button disabled={remoteBusy} onClick={()=>restoreFromTelegram(true)}>Analisar recuperação</button>{restorePreview&&<div className="dc-remote-restore-preview"><strong>Recuperação sem exclusões</strong><p>{restorePreview.checked} itens verificados • {restorePreview.new_items} itens ausentes neste computador • {restorePreview.existing_items} já existentes.</p><small>A recuperação adiciona apenas itens ausentes e não apaga ou sobrescreve arquivos. Confira se a conta e o canal são os corretos.</small><button className="dc-module-primary" disabled={remoteBusy||!restorePreview.new_items} onClick={()=>restoreFromTelegram(false)}>Confirmar recuperação de {restorePreview.new_items} itens</button></div>}{remoteSnapshot&&<p>Última cópia: {remoteSnapshot.items} itens • {remoteSnapshot.exported_at?new Date(remoteSnapshot.exported_at).toLocaleString('pt-BR'):'data indisponível'}. <a href={backendOrigin+'/api/cloud/catalog/telegram/download'} download="drive-cloud-telegram-catalog.json">Baixar JSON</a></p>}{remoteError&&<p className="public-share-error">{remoteError}</p>}</div>
 <small>A recuperação manual adiciona somente itens ausentes. A sincronização automática e a resolução de conflitos entre dispositivos ainda não estão disponíveis.</small>
 </div>}

 {section==='backups'&&<div className="dc-dashboard-grid"><div className="dc-module-card"><div className="dc-module-card-top"><DatabaseBackup size={20}/><span>Último backup</span></div><strong>{status?.last_backup?new Date(status.last_backup.created*1000).toLocaleString('pt-BR'):'Nenhum backup ainda'}</strong><small>{status?.last_backup?status.last_backup.item_count+' registros protegidos':'Crie o primeiro snapshot local do catálogo.'}</small></div><div className="dc-module-card"><div className="dc-module-card-top"><Clock3 size={20}/><span>Agendamento</span></div><strong>{frequency==='daily'?'Diário':frequency==='weekly'?'Semanal':'Desativado'}</strong><small>{status?.next_run?'Próxima execução: '+new Date(status.next_run*1000).toLocaleString('pt-BR'):'Executa enquanto o backend local estiver ligado.'}</small></div><div className="dc-module-card"><div className="dc-module-card-top"><List size={20}/><span>Histórico</span></div><strong>{history.length} snapshots</strong><small>Últimas cópias do catálogo neste computador.</small></div></div>}
 {(section==='backups'||section==='backupSchedule')&&<div className="dc-module-section"><div><h3>Backup do catálogo</h3><p>Faça uma cópia agora ou programe snapshots automáticos.</p></div><button className="dc-module-primary" disabled={loading} onClick={snapshot}><DatabaseBackup size={17}/>{loading?'Processando...':'Criar backup agora'}</button><div className="dc-schedule-controls"><label htmlFor="backup-frequency">Frequência</label><select className="dc-native-select" id="backup-frequency" disabled={loading||!status} value={frequency} onChange={e=>schedule(e.target.value)}><option value="off">Desativado</option><option value="daily">Diariamente</option><option value="weekly">Semanalmente</option></select><small>O computador e o backend precisam permanecer ligados para executar no horário programado.</small></div></div>}
 {(section==='backups'||section==='backupHistory')&&<div className="dc-module-section"><div><h3>Histórico de backups</h3><p>Baixe o JSON para guardar uma cópia fora do computador.</p></div><div className="dc-history-list">{history.length?history.map(x=><div className="dc-history-row" key={x.id}><DatabaseBackup size={19}/><div><strong>{new Date(x.created*1000).toLocaleString('pt-BR')}</strong><small>{x.item_count} registros • {size(x.bytes)} • {x.source==='scheduled'?'Automático':'Manual'}</small></div><a href={base+'/history/'+encodeURIComponent(x.id)+'/download'} title="Baixar snapshot"><Download size={17}/> Baixar</a></div>):<p className="dc-empty-message">Ainda não existem cópias do catálogo.</p>}</div></div>}</div>
}
function SyncPages({section,onToast}){
 const [folders,setFolders]=useState([]),[path,setPath]=useState(''),[preview,setPreview]=useState(null),[busy,setBusy]=useState(false),[running,setRunning]=useState(null),[error,setError]=useState(''),[lastResult,setLastResult]=useState(null);
 const [remoteRoots,setRemoteRoots]=useState([]),[selectedRoot,setSelectedRoot]=useState(''),[pullPreview,setPullPreview]=useState(null),[pullResult,setPullResult]=useState(null);
 async function request(endpoint,method='GET',payload){
  const response=await fetch(backendOrigin+'/api/sync'+endpoint,{method,headers:payload?{'Content-Type':'application/json'}:undefined,body:payload?JSON.stringify(payload):undefined});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Falha no serviço de sincronização.');
  return data;
 }
 async function refresh(){
  try{const [data,roots]=await Promise.all([request('/folders'),request('/remote-roots')]);setFolders(data.folders||[]);setRemoteRoots(roots.roots||[])}catch(e){setError(e.message)}
 }
 useEffect(()=>{refresh()},[]);
 async function browseFolder(){
  setError('');setPreview(null);
  try{
   if(!window.__TAURI_INTERNALS__){setError('Para escolher uma pasta do computador, abra o aplicativo instalado.');return}
   const selected=await openNativeDialog({directory:true,multiple:false,title:'Escolher pasta para backup no Telegram'});
   if(typeof selected==='string')setPath(selected);
  }catch(e){setError('Não foi possível abrir o seletor de pastas: '+String(e))}
 }
 async function inspect(){
  if(!path.trim())return;
  setBusy(true);setError('');setPreview(null);
  try{setPreview(await request('/folders/preview','POST',{path:path.trim()}))}
  catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function register(){
  if(!preview)return;
  setBusy(true);setError('');
  try{
   await request('/folders','POST',{path:preview.path,remote_root_id:selectedRoot||null});
   setPath('');setSelectedRoot('');setPreview(null);await refresh();
   onToast?.({kind:'success',message:'Pasta adicionada. O backup automático começa desativado.'});
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function runOne(folder){
  setRunning(folder.id);setError('');setLastResult(null);
  try{
   const check=await request('/folders/'+encodeURIComponent(folder.id)+'/preview','POST');
   if(!check.pending&&folder.mode!=='two-way'){onToast?.({kind:'info',message:'Nenhuma alteração pendente nesta pasta.'});return}
   const response=await request('/folders/'+encodeURIComponent(folder.id)+'/run','POST');
   setLastResult({path:folder.path,...response});
   onToast?.({kind:'success',message:response.sent+' arquivo(s) enviados'+(response.remote?', '+response.remote.downloaded+' recuperados e '+response.remote.conflicts+' conflitos preservados':'')+'. '+(response.remaining_estimate?'Execute novamente para continuar.':'')+(response.sent&&!response.catalog_snapshot_saved?' Atenção: catálogo remoto não foi atualizado; tente salvar em Backups.':'')});
   await refresh();
  }catch(e){setError(e.message)}finally{setRunning(null)}
 }
 async function updateCatalog(){
  setBusy(true);setError('');setPullPreview(null);
  try{
   const result=await request('/catalog/refresh','POST');
   await refresh();
   onToast?.({kind:'success',message:result.items_added+' registros recuperados do catálogo Telegram. '+(result.metadata_differences_preserved?'Mudanças divergentes foram preservadas localmente.':'')});
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function previewRemote(folder){
  setRunning(folder.id);setError('');setPullPreview(null);setPullResult(null);
  try{
   await request('/catalog/refresh','POST');
   const result=await request('/folders/'+encodeURIComponent(folder.id)+'/remote/preview','POST');
   setPullPreview({folder,...result});
   await refresh();
  }catch(e){setError(e.message)}finally{setRunning(null)}
 }
 async function pullRemote(folder){
  setRunning(folder.id);setError('');setPullResult(null);
  try{
   const result=await request('/folders/'+encodeURIComponent(folder.id)+'/pull','POST');
   setPullResult({folder,...result});setPullPreview(null);
   onToast?.({kind:'success',message:result.downloaded+' arquivos recuperados; '+result.conflicts+' cópias de conflito preservadas.'});
   await refresh();
  }catch(e){setError(e.message)}finally{setRunning(null)}
 }
 async function setMode(folder,mode){
  if(mode==='two-way'&&!confirm('Ativar sincronização bidirecional para esta pasta? Arquivos remotos podem ser baixados para o PC, mas não serão sobrescritos: versões diferentes são preservadas. Use primeiro com arquivos de teste.'))return;
  setBusy(true);setError('');
  try{
   await request('/folders/'+encodeURIComponent(folder.id)+'/mode','POST',{mode});
   await refresh();
   onToast?.({kind:'info',message:mode==='two-way'?'Modo bidirecional ativado.':'Modo backup ativado.'});
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function removeOne(folder){
  if(!confirm('Remover esta pasta do monitoramento? Os arquivos já enviados ao Telegram serão preservados.'))return;
  setBusy(true);setError('');
  try{await request('/folders/'+encodeURIComponent(folder.id),'DELETE');await refresh();
   onToast?.({kind:'success',message:'Pasta desconectada do backup. Os arquivos no Telegram foram preservados.'});
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function toggleAuto(folder,enabled){
  setBusy(true);setError('');
  try{await request('/folders/'+encodeURIComponent(folder.id)+'/automatic','POST',{enabled});await refresh();
   onToast?.({kind:'info',message:enabled?'Backup automático ativado para esta pasta.':'Backup automático pausado.'});
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return <div className="dc-module-page">
  <div className="dc-module-note"><RefreshCw size={20}/><div><strong>Pastas do computador</strong><p>Backup e recuperação de arquivos por pasta, com opção de sincronização em duas direções. O Drive Cloud não exclui arquivos do Telegram ao apagar itens no computador e não sobrescreve arquivos locais em caso de conflito.</p></div></div>
  {error&&<div className="public-share-error" role="alert">{error}</div>}
  {section==='sync'&&<div className="dc-module-section dc-local-folder-setup"><h3>Adicionar pasta</h3><p>Escolha uma pasta. Primeiro analisaremos os arquivos e mostraremos o que poderá ser enviado; nada é enviado até você confirmar.</p>
   <div className="dc-folder-path-row"><input aria-label="Pasta do computador" value={path} onChange={e=>{setPath(e.target.value);setPreview(null)}} placeholder="Selecione uma pasta do computador"/><button type="button" disabled={busy} onClick={browseFolder}><Folder size={15}/> Procurar</button><button type="button" disabled={busy||!path.trim()} onClick={inspect}>Analisar</button></div>
   <button type="button" className="dc-sync-refresh" disabled={busy||!!running} onClick={updateCatalog}><RefreshCw size={15}/> Buscar backups de outros dispositivos no Telegram</button>
   {remoteRoots.length>0&&<label className="dc-remote-root-selection">Origem do backup
     <select value={selectedRoot} onChange={e=>setSelectedRoot(e.target.value)}>
      <option value="">Criar novo backup no Telegram</option>
      {remoteRoots.map(root=><option key={root.id} value={root.id}>{root.name}</option>)}
     </select><small>Clique em Buscar backups para localizar pastas de outros dispositivos. Depois selecione aqui a pasta existente, sem duplicar o armazenamento.</small>
    </label>}
   {preview&&<div className="dc-folder-preview"><strong>{preview.files} arquivos • {size(preview.bytes)}</strong><small>{preview.over_limit?preview.over_limit+' arquivo(s) acima de 512 MB serão ignorados.':'Nenhum arquivo acima de 512 MB.'}</small><button className="dc-module-primary" disabled={busy} onClick={register}>Adicionar ao Drive Cloud</button></div>}
  </div>}
  <div className="dc-module-section"><h3>{section==='devices'?'Pastas neste dispositivo':section==='syncActivity'?'Atividade de backup':'Pastas configuradas'}</h3><p>O Drive Cloud envia e recupera até três arquivos por execução; no modo duas direções, consulta os snapshots do catálogo e preserva arquivos divergentes com nomes diferentes. O monitoramento automático roda a cada dois minutos quando ativado.</p>
   <div className="dc-folder-sync-list">{folders.length?folders.map(folder=><div className="dc-folder-sync-item" key={folder.id}><div className="dc-folder-sync-title"><Folder size={19}/><div><strong>{folder.path.split(/[\\/]/).filter(Boolean).at(-1)||folder.path}</strong><small title={folder.path}>{folder.path}</small></div></div>
    <div className="dc-folder-sync-actions"><span>{folder.enabled?'Backup automático ligado':'Backup automático pausado'}{folder.last_run?' • Última execução: '+new Date(folder.last_run*1000).toLocaleString('pt-BR'):''}</span><button disabled={!!running||busy} onClick={()=>runOne(folder)}>{running===folder.id?'Enviando...':'Sincronizar agora'}</button><button type="button" disabled={!!running||busy} onClick={()=>previewRemote(folder)}>Recuperar do Telegram</button><label className="dc-sync-mode">Modo <select aria-label={'Modo de sincronização de '+folder.path} disabled={!!running||busy} value={folder.mode||'backup'} onChange={e=>setMode(folder,e.target.value)}><option value="backup">Backup (PC → Telegram)</option><option value="two-way">Duas direções (PC ↔ Telegram)</option></select></label><label><input type="checkbox" disabled={!!running||busy} checked={!!folder.enabled} onChange={e=>toggleAuto(folder,e.target.checked)}/> Automático</label><button type="button" disabled={!!running||busy} onClick={()=>removeOne(folder)}>Remover da lista</button></div>
    {folder.last_error&&<small className="dc-sync-error">{folder.last_error}</small>}</div>):<p className="dc-empty-message">Nenhuma pasta configurada neste dispositivo.</p>}</div>
   {pullPreview&&<div className="dc-folder-preview"><strong>Recuperação de {pullPreview.folder.path.split(/[\\/]/).filter(Boolean).at(-1)}</strong><p>{pullPreview.pending} arquivo(s) para verificar • até {pullPreview.conflicts_possible} possíveis conflitos • {pullPreview.over_limit} acima do limite.</p><small>O Drive Cloud preserva as versões locais. Arquivos divergentes serão salvos com o sufixo (Telegram-...). Não haverá exclusões.</small><button className="dc-module-primary" onClick={()=>pullRemote(pullPreview.folder)} disabled={!!running||busy||!pullPreview.pending}>Confirmar recuperação</button></div>}
   {pullResult&&<p className="dc-sync-result">Recuperação: {pullResult.downloaded} baixados, {pullResult.identical} iguais, {pullResult.conflicts} conflitos preservados. {pullResult.remaining_estimate} pendentes estimados.</p>}
   {lastResult&&<p className="dc-sync-result">{lastResult.sent} arquivo(s) enviados da pasta {lastResult.path}. {lastResult.remaining_estimate} pendentes estimados. As exclusões locais não afetam o Telegram.</p>}
  </div>
  {section==='devices'&&<div className="dc-module-note"><HardDrive size={18}/><div><strong>Outros dispositivos</strong><p>A sincronização em duas direções já permite recuperar arquivos do catálogo e guardar cópias de conflitos. Para usar dois computadores, recupere primeiro o catálogo em Backups e vincule a mesma pasta remota. Sincronização contínua de catálogos entre aparelhos ainda está em desenvolvimento.</p></div></div>}
 </div>
}
function SettingsPages({section,onToast}){
 const [compact,setCompact]=useState(()=>localStorage.getItem('dc-compact')==='true');
 const [preferredLayout,setPreferredLayout]=useState(readDriveLayout);
 const [motion,setMotion]=useState(()=>localStorage.getItem('dc-reduce-motion')==='true');
 const [links,setLinks]=useState([]),[error,setError]=useState('');
 useEffect(()=>{document.documentElement.classList.toggle('dc-compact-ui',compact);document.documentElement.classList.toggle('dc-less-motion',motion)},[]);
 async function refresh(){try{const res=await fetch(backendOrigin+'/api/share');if(res.ok)setLinks((await res.json()).links||[])}catch{}}
 useEffect(()=>{refresh()},[]);
 function changeCompact(value){setCompact(value);localStorage.setItem('dc-compact',String(value));document.documentElement.classList.toggle('dc-compact-ui',value);onToast?.({kind:'success',message:'Densidade visual atualizada.'})}
 function changePreferredLayout(value){setPreferredLayout(value);localStorage.setItem('dc-file-layout',value);window.dispatchEvent(new CustomEvent('drive-layout-updated',{detail:value}));onToast?.({kind:'success',message:'Visualização padrão atualizada.'})}
 function changeMotion(value){setMotion(value);localStorage.setItem('dc-reduce-motion',String(value));document.documentElement.classList.toggle('dc-less-motion',value);onToast?.({kind:'success',message:'Preferência de animação atualizada.'})}
 async function revoke(id){try{const r=await fetch(backendOrigin+'/api/share/'+id,{method:'DELETE'});if(!r.ok)throw Error('Falha ao revogar link');await refresh();onToast?.({kind:'success',message:'Compartilhamento revogado.'})}catch(e){setError(e.message)}}
 return <div className="dc-module-page">
 {section==='settings'&&<div className="dc-dashboard-grid"><div className="dc-module-card"><div className="dc-module-card-top"><Cloud size={20}/><span>Armazenamento</span></div><strong>Telegram privado</strong><small>Controle de conexão e canal no menu Conexão Telegram.</small></div><div className="dc-module-card"><div className="dc-module-card-top"><DatabaseBackup size={20}/><span>Backups</span></div><strong>Snapshots locais</strong><small>Configure cópias de segurança do catálogo em Backups.</small></div><div className="dc-module-card"><div className="dc-module-card-top"><Users size={20}/><span>Compartilhamentos</span></div><strong>{links.filter(x=>!x.revoked&&x.expires>Date.now()/1000).length} links ativos</strong><small>Revogue links antes de compartilhar novamente.</small></div></div>}
 {(section==='settings'||section==='preferences')&&<div className="dc-module-section"><h3>Aparência</h3><p>Preferências salvas somente neste navegador.</p><div className="dc-option-row"><span><strong>Visualização de arquivos</strong><small>Modo padrão ao abrir o Meu Drive.</small></span><div className="dc-select-wrap"><select aria-label="Visualização padrão" value={preferredLayout} onChange={e=>changePreferredLayout(e.target.value)}><option value="list">Lista</option><option value="grid">Grade</option></select><ChevronDown size={15}/></div></div><label className="dc-option-row"><span><strong>Interface compacta</strong><small>Reduz espaçamentos das listas e ferramentas.</small></span><input type="checkbox" checked={compact} onChange={e=>changeCompact(e.target.checked)}/></label><label className="dc-option-row"><span><strong>Reduzir animações</strong><small>Transições mais discretas para navegação e modais.</small></span><input type="checkbox" checked={motion} onChange={e=>changeMotion(e.target.checked)}/></label></div>}
 {(section==='settings'||section==='security')&&<div className="dc-module-section"><h3>Segurança e compartilhamentos</h3><p>O serviço do Drive Cloud aceita somente conexões locais. Nunca exponha os arquivos de sessão ou a API administrativa na internet.</p>{error&&<p className="public-share-error">{error}</p>}<div className="dc-history-list">{links.filter(x=>!x.revoked&&x.expires>Date.now()/1000).map(x=><div className="dc-history-row" key={x.id}><Users size={18}/><div><strong>{x.name||'Item indisponível'}</strong><small>{x.mode==='download'?'Download':'Compartilhado'} • expira em {new Date(x.expires*1000).toLocaleString('pt-BR')}</small></div><button onClick={()=>revoke(x.id)}>Revogar</button></div>)}{!links.some(x=>!x.revoked&&x.expires>Date.now()/1000)&&<p className="dc-empty-message">Nenhum compartilhamento ativo.</p>}</div></div>}</div>
}
function DriveFolderTree({nodes,current,onOpen}){
 const [expanded,setExpanded]=useState({});
 const listRef=useRef(null);
 const activeRowRef=useRef(null);
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
 useEffect(()=>{
  // The selected folder may sit at the end of a long, animated tree.
  // Keep it visible without scrolling the entire page or stealing focus.
  if(!current)return;
  const timer=window.setTimeout(()=>{
   const list=listRef.current,row=activeRowRef.current;
   if(!list||!row)return;
   const bounds=list.getBoundingClientRect(),rect=row.getBoundingClientRect();
   if(rect.top<bounds.top+8)list.scrollTop+=rect.top-bounds.top-8;
   else if(rect.bottom>bounds.bottom-20)list.scrollTop+=rect.bottom-bounds.bottom+20;
   if(rect.left<bounds.left+8)list.scrollLeft+=rect.left-bounds.left-8;
   else if(rect.right>bounds.right-12)list.scrollLeft+=rect.right-bounds.right+12;
  },300);
  return()=>window.clearTimeout(timer);
 },[current,nodes]);
 function branch(parent,depth){
  if(depth>22)return null;
  return folders.filter(x=>(x.parent||null)===parent).sort((a,b)=>a.name.localeCompare(b.name,'pt-BR')).map(item=>{
   const children=folders.some(x=>x.parent===item.id);
   const open=!!expanded[item.id];
   return <div key={item.id} className="dc-tree-branch">
    <div className={'dc-tree-row '+(current===item.id?'active':'')} style={{paddingLeft:(8+depth*14)+'px'}} title={item.name}>
     <button className="dc-tree-expand" title={children?(open?'Recolher pasta':'Expandir pasta'):'Sem subpastas'} disabled={!children} onClick={()=>setExpanded(prev=>({...prev,[item.id]:!prev[item.id]}))}>{children?(open?<ChevronDown size={14}/>:<ChevronRight size={14}/>):<span/>}</button>
     <button ref={current===item.id?activeRowRef:null} className="dc-tree-name" title={item.name} onClick={()=>{onOpen(item.id);setExpanded(prev=>({...prev,[item.id]:true}))}}><Folder size={16}/><span>{item.name}</span></button>
    </div>
    {children&&<div className={'dc-tree-children '+(open?'expanded':'')}><div className="dc-tree-children-inner">{branch(item.id,depth+1)}</div></div>}
   </div>
  })
 }
 return <div className="dc-folder-tree"><div className="dc-folder-tree-heading">Pastas <span>{folders.length}</span></div>
 <button className={'dc-tree-root '+(current===null?'active':'')} onClick={()=>onOpen(null)}><Folder size={16}/><span>Raiz do Meu Drive</span></button>
 <div className="dc-tree-list" ref={listRef}>{branch(null,0)}</div></div>
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
const driveSections=['cloudFiles','home','recent','starred','trash'];const [createFolderToken,setCreateFolderToken]=useState(0);const [cloudTree,setCloudTree]=useState([]);const [cloudFolder,setCloudFolder]=useState(null);const [folderTarget,setFolderTarget]=useState(()=>initialRoute.current.folder?{id:initialRoute.current.folder,nonce:1}:null);const [deletionProgress,setDeletionProgress]=useState(null);const [toast,setToast]=useState(null);const showToast=t=>setToast({...t,id:crypto.randomUUID()});const [telegramConnected,setTelegramConnected]=useState(false);const [telegramAccountId,setTelegramAccountId]=useState(null);const [driveUsage,setDriveUsage]=useState(null);const[items,setItems]=useState([]),[section,setSection]=useState(()=>initialRoute.current.page),[area,setArea]=useState(()=>({home:'home',recent:'home',starred:'home',cloudFiles:'files',trash:'trash',backups:'backups',backupHistory:'backups',backupSchedule:'backups',sync:'sync',devices:'sync',syncActivity:'sync',settings:'settings',telegram:'settings',security:'settings',preferences:'settings'})[initialRoute.current.page]||'home'),[folder,setFolder]=useState(null),[view,setView]=useState(readDriveLayout),[query,setQuery]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[mobile,setMobile]=useState(false);
const input=useRef(null);
const refresh=async()=>setItems(await all());
useEffect(()=>{refresh().catch(e=>setNotice('Falha ao abrir o armazenamento: '+e.message));
const refreshTelegram=async()=>{try{const status=await fetch(backendOrigin+'/api/telegram/status').then(r=>r.json());setTelegramConnected(!!status.connected);setTelegramAccountId(status.connected&&status.id?String(status.id):null);
if(status.connected){const response=await fetch(backendOrigin+'/api/cloud/usage');if(response.ok)setDriveUsage(await response.json())}
else setDriveUsage(null)}catch{setTelegramConnected(false);setTelegramAccountId(null);setDriveUsage(null)}};
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
return <div className="shell"><aside className="rail"><div className="logo" title="Drive Cloud"><img src="/drive-cloud-logo.svg?v=20261120b" alt="Drive Cloud"/></div>{primary.map(([a,name,Icon])=><button key={a} title={name} aria-label={name} className={area===a?'rail-on':''} onClick={()=>goArea(a)}><Icon size={21}/></button>)}</aside>
<aside className={'sidebar '+(mobile?'show':'')+(area==='files'?' sidebar-tree':'')}><div className="sidebar-title">{primary.find(p=>p[0]===area)?.[1]||'Meu espaço'}<button className="mobile-x" onClick={()=>setMobile(false)}><X size={19}/></button></div><div className="links">{menus[area].map(([id,name,Icon])=><button key={id} className={section===id?'active':''} onClick={()=>nav(id)}><Icon size={18}/>{name}</button>)}</div>{area==='files'&&<DriveFolderTree nodes={cloudTree} current={cloudFolder} onOpen={id=>{nav('cloudFiles',id)}}/>}<div className="sidebar-bottom"><div className="dc-compact-storage">
<div className="dc-usage-heading"><HardDrive size={16}/><span>Armazenamento</span></div>
<div className="dc-usage-value">{driveUsage?size(driveUsage.total_bytes):'—'} <small>utilizados no Drive / <span title="O Telegram não informa uma cota de armazenamento para esta integração.">Sem cota informada</span></small></div>
<div className="dc-usage-breakdown"><span><i className="active"/> Arquivos {driveUsage?size(driveUsage.active_bytes||0):'—'}</span><span><i className="trash"/> Lixeira {driveUsage?size(driveUsage.trash_bytes||0):'—'}</span></div>
<div className="dc-usage-status"><i className={telegramConnected?'connected':'disconnected'}/>{telegramConnected?'Telegram conectado':'Telegram desconectado'}</div>
</div></div></aside>
<main><header><button className="mobile-toggle" onClick={()=>setMobile(!mobile)}>☰</button>{section==='cloudFiles'&&<button className="new" title="Criar pasta no Meu Drive" onClick={()=>{nav('cloudFiles');setCreateFolderToken(n=>n+1)}}><Plus size={18}/> Novo</button>}{['cloudFiles','home','recent','starred'].includes(section)&&<div className="search"><Search size={18}/><input placeholder="Buscar arquivos e pastas..." value={query} onChange={e=>setQuery(e.target.value)}/></div>}<span className="avatar" title={telegramConnected?"Conta Telegram conectada":"Drive Cloud"}>DC{telegramConnected&&telegramAccountId&&<img key={telegramAccountId} src={backendOrigin+"/api/telegram/avatar?account="+encodeURIComponent(telegramAccountId)} alt="Foto do perfil Telegram" onError={e=>{e.currentTarget.style.display="none"}}/>}</span></header>
<div className="content"><div className="heading"><div><h1>{trail.length&&section==='files'?trail.at(-1).name:label}</h1>{!driveSections.includes(section)&&<p>{section==='telegram'?'Gerencie a conta e o canal privado usados pelo Drive.':area==='backups'?'Agendamentos e histórico de cópias do catálogo.':area==='sync'?'Gerencie as opções de sincronização entre dispositivos.':'Preferências e segurança do Drive Cloud.'}</p>}</div></div>
<div style={{display:driveSections.includes(section)?'block':'none'}}><CloudFiles mode={section==='cloudFiles'?'files':driveSections.includes(section)?section:'files'} globalSearch={query} onToast={showToast} onDeletionProgress={setDeletionProgress} createFolderToken={createFolderToken} onCatalogChange={setCloudTree} onFolderChange={updateDriveFolder} folderTarget={folderTarget} onInitialReady={()=>setInitialReady(true)} onNavigateFolder={id=>nav('cloudFiles',id)}/></div>{section==='telegram'?<TelegramSettings onToast={showToast}/>:['backups','backupSchedule','backupHistory'].includes(section)?<BackupPages section={section} onToast={showToast}/>:['sync','devices','syncActivity'].includes(section)?<SyncPages section={section} onToast={showToast}/>:['settings','security','preferences'].includes(section)?<SettingsPages section={section} onToast={showToast}/>:!driveSections.includes(section)&&!['backups','backupSchedule','backupHistory','sync','devices','syncActivity','settings','security','preferences'].includes(section)?<><div className="toolbar"><div className="chips"><button onClick={()=>nav('recent')}><Clock3 size={15}/> Recentes</button><button onClick={()=>nav('starred')}><Star size={15}/> Favoritos</button></div><div className="toggle"><button aria-label="Modo grade" className={view==='grid'?'chosen':''} onClick={()=>setView('grid')}><Grid2X2 size={18}/></button><button aria-label="Modo lista" className={view==='list'?'chosen':''} onClick={()=>setView('list')}><List size={18}/></button></div></div>
{visible.length===0?<div className="empty"><Folder size={50}/><h3>Nenhum arquivo por aqui</h3><p>{['shared','sync','backupHistory','backupSchedule','devices','syncActivity','settings','telegram','security','preferences'].includes(section)?'Este recurso será adicionado em uma próxima etapa.':'Envie arquivos ou crie uma pasta para começar.'}</p></div>:view==='grid'?<div className="grid">{visible.map(i=><article key={i.id} className="tile"><button className="more" aria-label={'Opções de '+i.name} onClick={()=>{const action=window.prompt('Ação: '+(i.trashed?'restaurar, excluir':'abrir, favorito, lixeira'));if(!action)return;if(action==='abrir')open(i);else act(i,({favorito:'star',lixeira:'trash',restaurar:'restore',excluir:'delete'})[action]||action)}}><MoreHorizontal size={20}/></button><div className="tile-icon" onDoubleClick={()=>open(i)}><IconFile item={i} large/></div><button className="tile-name" onClick={()=>open(i)} title={i.name}>{i.name}</button><small>{i.kind==='folder'?'Pasta':size(i.size)} {i.starred?'★':''}</small></article>)}</div>:<div className="table-scroll"><div className="table"><div className="table-head"><span>Nome</span><span>Modificado</span><span>Tamanho</span><span>Ações</span></div>{visible.map(i=><div className="table-row" key={i.id}><button onClick={()=>open(i)}><IconFile item={i}/><span>{i.name} {i.starred?'★':''}</span></button><span>{date(i.time)}</span><span>{i.kind==='folder'?'—':size(i.size)}</span><div className="row-actions">{i.trashed?<><button title="Restaurar" onClick={()=>act(i,'restore')}>↶</button><button title="Excluir definitivamente" onClick={()=>act(i,'delete')}><Trash2 size={16}/></button></>:<><button title="Favorito" onClick={()=>act(i,'star')}><Star size={16} fill={i.starred?'#bca3f2':'none'}/></button><button title="Mover para lixeira" onClick={()=>act(i,'trash')}><Trash2 size={16}/></button></>}</div></div>)}</div></div>}
</>:null}<footer>{['cloudFiles','home','recent','starred'].includes(section)?'Arquivos no Telegram • Catálogo armazenado neste dispositivo':'Mantenha outra cópia dos arquivos importantes'} <span>Drive Cloud</span></footer></div></main><input ref={input} type="file" multiple hidden onChange={e=>upload([...e.target.files])}/><DriveToast toast={deletionProgress?null:toast} progress={deletionProgress} onDismiss={()=>setToast(null)}/>{!initialReady&&<div className="dc-initial-splash" role="status" aria-label="Carregando Drive Cloud" aria-busy="true"><DriveBrandLoader/></div>}</div>}
const params=new URLSearchParams(window.location.search);
const matchShare=window.location.pathname.match(/^\/(?:file|folder)\/d\/([A-Za-z0-9_-]+)\/?$/),matchEmbed=window.location.pathname.match(/^\/embed\/d\/([A-Za-z0-9_-]+)\/?$/);
const publicToken=matchShare?.[1]||params.get('share'),embedToken=matchEmbed?.[1]||params.get('embed');
async function startDriveCloud() {
  if (window.__TAURI_INTERNALS__) {
    try {
      // This is provided by the desktop host, not discovered through random
      // ports or exposed by a public endpoint.
      backendOrigin = await invoke('backend_origin');
    } catch (error) {
      console.error('Não foi possível descobrir a porta do backend local.', error);
    }
  }
  createRoot(document.getElementById('root')).render(embedToken?<EmbeddedMedia token={embedToken}/>:publicToken?<PublicShareView token={publicToken}/>:<App/>);
}
startDriveCloud();