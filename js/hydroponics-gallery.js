(() => {
 const modal=document.getElementById('hydroLightbox');
 const img=modal.querySelector('img');
 const caption=modal.querySelector('.hydro-lightbox-caption');
 const counter=modal.querySelector('.hydro-lightbox-counter');
 const close=modal.querySelector('.hydro-lightbox-close');
 const prev=modal.querySelector('.hydro-lightbox-prev');
 const next=modal.querySelector('.hydro-lightbox-next');
 const buttons=[...document.querySelectorAll('.hydro-photo-button')];
 let group=[],current=0,opener=null,touchX=null;
 function show(n){current=(n+group.length)%group.length;const b=group[current];img.src=b.dataset.src;img.alt=b.querySelector('img').alt;caption.textContent=b.dataset.caption;counter.textContent=`${current+1} / ${group.length}`;}
 function open(b){opener=b;group=buttons.filter(x=>x.dataset.gallery===b.dataset.gallery);show(group.indexOf(b));modal.classList.add('open');modal.setAttribute('aria-hidden','false');document.body.style.overflow='hidden';close.focus();}
 function shut(){modal.classList.remove('open');modal.setAttribute('aria-hidden','true');img.removeAttribute('src');document.body.style.overflow='';opener?.focus();}
 buttons.forEach(b=>b.addEventListener('click',()=>open(b)));
 close.addEventListener('click',shut);prev.addEventListener('click',()=>show(current-1));next.addEventListener('click',()=>show(current+1));
 modal.addEventListener('click',e=>{if(e.target===modal)shut();});
 document.addEventListener('keydown',e=>{if(!modal.classList.contains('open'))return;if(e.key==='Escape')shut();if(e.key==='ArrowLeft')show(current-1);if(e.key==='ArrowRight')show(current+1);if(e.key==='Tab'){const controls=[close,prev,next];const i=controls.indexOf(document.activeElement);if(e.shiftKey&&i===0){e.preventDefault();next.focus();}else if(!e.shiftKey&&i===2){e.preventDefault();close.focus();}}});
 modal.addEventListener('touchstart',e=>{touchX=e.changedTouches[0].screenX;},{passive:true});
 modal.addEventListener('touchend',e=>{if(touchX===null)return;const dx=e.changedTouches[0].screenX-touchX;if(Math.abs(dx)>55)show(current+(dx<0?1:-1));touchX=null;},{passive:true});
})();
