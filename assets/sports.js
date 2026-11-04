/* Shared frame for the racing, soccer and tennis pages: day navigation, the ledger strip, the slips, filter
   chips and the card list. Each page passes what's specific to its sport. */
(function(){
'use strict';
var $=function(s){return document.querySelector(s);};
var H={
  esc:function(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});},
  pct:function(p){return Math.round(p*100)+'%';},
  fair:function(p){return p>0?(1/p).toFixed(2):'–';},
  eur:function(x){return (x>=0?'+':'−')+'€'+Math.abs(x).toFixed(2);},
  cls:function(x){return x>0?'gain':x<0?'loss':'';},
  /* A ledger tile: what was measured, how many of how many, and the € on €1 stakes (est. when estimated). */
  tile:function(label,hits,of,pl,est){
    return '<div class="tile"><span class="k">'+H.esc(label)+'</span><b class="v">'+hits+'<small>/'+of+'</small></b>'+
      (pl==null?'<span class="pl">&nbsp;</span>':'<span class="pl '+H.cls(pl)+'">'+H.eur(pl)+(est?'<span class="est">est.</span>':'')+'</span>')+'</div>';
  },
  leg:function(state,title,sub,odds){
    var box=state===true?'✓':state===false?'✗':'';
    return '<li class="leg'+(state===true?' ok':state===false?' no':'')+'"><span class="box" aria-hidden="true">'+box+'</span>'+
      '<div><b>'+title+'</b><span>'+sub+'</span></div>'+(odds?'<em class="odds">'+odds+'</em>':'<span></span>')+'</li>';
  },
  hit:function(h,label){
    if(h==null)return '<span></span>';
    return '<span class="hit '+(h?'ok':'no')+'" title="'+H.esc(label||'')+'">'+(h?'✓':'✗')+'</span>';
  }
};
var pad=function(n){return String(n).padStart(2,'0');};
var keyOf=function(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());};
var fromKey=function(k){var p=String(k).split('-').map(Number);return new Date(p[0],p[1]-1,p[2]);};
var getJSON=function(u){return fetch(u,{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error(r.status);return r.json();});};
H.nowLondon=function(){
  try{return new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date());}
  catch(e){var d=new Date();return pad(d.getHours())+':'+pad(d.getMinutes());}
};

window.SportsPage=function(cfg){
  var dates=[],cur=null,day=null,group=null,today=keyOf(new Date());
  function render(){
    var i=dates.indexOf(cur);
    $('#prev').disabled=i<=0;
    $('#next').disabled=i<0||i>=dates.length-1;
    $('#today').hidden=cur===today||dates.indexOf(today)<0;
    $('#title').textContent=cur?fromKey(cur).toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'}):cfg.name;
    $('#when').innerHTML=cur===today?'<span class="live">Today</span>':cur&&cur>today?'Coming up':cur?'Results':'';
    var items=day?cfg.items(day)||[]:[];
    if(!items.length){
      $('#ledger').hidden=$('#slips').hidden=$('#filters').hidden=true;
      $('#cards').innerHTML='<div class="empty"><b>'+(dates.length?'Nothing on this day':'No picks yet')+'</b>'+
        H.esc(dates.length?'Use the arrows to see another day.':cfg.emptyText)+'</div>';
      return;
    }
    var counts={};items.forEach(function(x){var g=cfg.groupOf(x);counts[g]=(counts[g]||0)+1;});
    var groups=Object.keys(counts).sort();
    H.colour=function(g){return 'var(--s'+(groups.indexOf(g)%8+1)+')';};
    if(group&&!counts[group])group=null;
    var now=cur===today?H.nowLondon():null;
    H.now=now;
    var led=cfg.ledger(day,items,H)||'';
    $('#ledger').hidden=!led;$('#ledger').innerHTML=led;
    var sl=cfg.slips(day,items,H)||'';
    $('#slips').hidden=!sl;$('#slips').innerHTML=sl;
    $('#filters').hidden=groups.length<2;
    $('#filters').innerHTML='<button class="chip all" type="button" data-g="" aria-pressed="'+(!group)+'">All <em>'+items.length+'</em></button>'+
      groups.map(function(g){return '<button class="chip" type="button" data-g="'+H.esc(g)+'" style="--k:'+H.colour(g)+'" aria-pressed="'+(group===g)+'">'+H.esc(g)+' <em>'+counts[g]+'</em></button>';}).join('');
    var shown=items.filter(function(x){return !group||cfg.groupOf(x)===group;});
    var over=function(x){return cfg.over(x,now);};
    if(now)shown=shown.filter(function(x){return !over(x);}).concat(shown.filter(over));
    $('#cards').innerHTML=shown.map(function(x){return cfg.card(x,H,!!(now&&over(x)));}).join('');
  }
  function show(k){
    cur=k;day=null;render();
    if(!k)return;
    getJSON('picks/'+k+'.json').then(function(d){if(cur===k){day=d;render();}}).catch(function(){if(cur===k)render();});
  }
  $('#prev').addEventListener('click',function(){var i=dates.indexOf(cur);if(i>0)show(dates[i-1]);});
  $('#next').addEventListener('click',function(){var i=dates.indexOf(cur);if(i>=0&&i<dates.length-1)show(dates[i+1]);});
  $('#today').addEventListener('click',function(){show(today);});
  $('#filters').addEventListener('click',function(e){var b=e.target.closest('.chip');if(!b)return;group=b.dataset.g||null;render();});
  getJSON('picks/index.json').then(function(ix){
    dates=(ix&&ix.dates)||[];
    var next=dates.filter(function(d){return d>=today;})[0];
    show(dates.indexOf(today)>=0?today:next||dates[dates.length-1]||null);
  }).catch(function(){dates=[];show(null);});
};
})();
