
// Ocultar entradas de navegación para Residente (2) y Visor (4)
(function(){
  if ([2,4].includes(window.SNB_USER_ROLE_ID)){
    const selectors = ['a[href*="/usuarios"]','a[href*="/roles"]','a[href*="/areas"]','a[href*="/area"]'];
    document.querySelectorAll(selectors.join(',')).forEach(el=>{ el.style.display='none'; });
  }
})();


// Ocultar "Nueva reservación" si el rol es VISOR (3)
(function(){
  if (window.SNB_USER_ROLE_ID === 4) {
    // Buscar botón por id conocido o por texto
    var btn = document.getElementById("btnNuevaReservacion") || document.getElementById("btnNuevaReserva");
    if (!btn){
      // intenta localizar por texto
      var candidates = Array.from(document.querySelectorAll("a,button"));
      btn = candidates.find(el => /Nueva reservación/i.test(el.textContent||""));
    }
    if (btn) btn.style.display = "none";
  }
})();


(function(){
  const grid = document.getElementById("calendarGrid");
  if (!grid) return;

  const rangeEl = document.getElementById("weekRange");
  const prevBtn = document.getElementById("prevWeek");
  const nextBtn = document.getElementById("nextWeek");
  const todayBtn = document.getElementById("todayBtn");

  const startHour = 7;
  const endHour = 22;
  const daysCount = 7;

  let current = new Date();
  const __now = new Date();
  const __minYear = __now.getFullYear()-1;
  const __maxYear = __now.getFullYear()+1;

  function startOfWeek(d){
    const date = new Date(d);
    const day = (date.getDay() + 6) % 7;
    date.setDate(date.getDate() - day);
    date.setHours(0,0,0,0);
    return date;
  }
  function formatRangeText(startDate){
    const endDate = new Date(startDate);
    endDate.setDate(endDate.getDate() + 6);
    const fmt = new Intl.DateTimeFormat('es-ES', { day:'numeric', month:'long', year:'numeric' });
    const fmtNoYear = new Intl.DateTimeFormat('es-ES', { day:'numeric', month:'long' });
    let text;
    if (startDate.getFullYear() === endDate.getFullYear()){
      text = `${fmtNoYear.format(startDate)} – ${fmt.format(endDate)}`;
    } else {
      text = `${fmt.format(startDate)} – ${fmt.format(endDate)}`;
    }
    return text;
  }
  function buildGrid(forDate){
    grid.innerHTML = "";
    const weekStart = startOfWeek(forDate);
    window.__SNB_WEEK_START = new Date(weekStart);
    const corner = document.createElement("div");
    corner.className = "cal-head sticky-header sticky-hours";
    corner.style.gridColumn = "1 / 2";
    corner.style.gridRow = "1 / 2";
    grid.appendChild(corner);

    const dayNames = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];
    const __today = new Date(); __today.setHours(0,0,0,0);
    for(let i=0;i<daysCount;i++){
      const d = new Date(weekStart);
      d.setDate(weekStart.getDate()+i);
      const head = document.createElement("div");
      head.className = "cal-head sticky-header";
      head.style.gridColumn = (i+2) + " / " + (i+3);
      head.style.gridRow = "1 / 2";
      head.innerHTML = `<div class="dayname">${dayNames[i]}</div><div class="daynum">${d.getDate()}</div>`;
      // highlight today header
      const _d = new Date(d); _d.setHours(0,0,0,0);
      if (_d.getTime() === __today.getTime()) { head.classList.add('is-today'); }
      grid.appendChild(head);
    }

    let rowIndex = 2;
    for(let h=startHour; h<endHour; h++){
      const hourCell = document.createElement("div");
      hourCell.className = "hour-cell sticky-hours";
      hourCell.style.gridColumn = "1 / 2";
      hourCell.style.gridRow = rowIndex + " / " + (rowIndex+1);
      const label = (h<10? "0"+h : h) + ":00";
      hourCell.textContent = label;
      grid.appendChild(hourCell);

      for(let c=0;c<daysCount;c++){
        const slot = document.createElement("div");
        slot.className = "slot";
        const td = new Date(weekStart); td.setDate(weekStart.getDate()+c); td.setHours(0,0,0,0);
        if (td.getTime() === __today.getTime()) { slot.classList.add('is-today-col'); }
        slot.style.gridColumn = (c+2) + " / " + (c+3);
        slot.style.gridRow = rowIndex + " / " + (rowIndex+1);
        grid.appendChild(slot);
      }
      rowIndex++;
    }
    rangeEl.textContent = formatRangeText(weekStart);
  }

  if (prevBtn) prevBtn.addEventListener("click", ()=>{ current.setDate(current.getDate() - 7); buildGrid(current); });
  if (nextBtn) nextBtn.addEventListener("click", ()=>{ current.setDate(current.getDate() + 7); buildGrid(current); });
  if (todayBtn) todayBtn.addEventListener("click", ()=>{ current = new Date(); buildGrid(current); });

  
  const pickerBtn = document.getElementById("rangePickerBtn");
  const pop = document.getElementById("rangePopover");
  const areaSelect = document.getElementById("areaSelect");
  if (areaSelect){
    areaSelect.addEventListener("change", ()=>{
      const area = areaSelect.value;
      const params = new URLSearchParams(window.location.search);
      if (area) params.set("area_id", area); else params.delete("area_id");
      window.location.search = params.toString();
    });
  }

  function openPicker(){
    if (!pop) return;
    pop.hidden = false;
    const anchor = document.getElementById("weekRange");
    const r = anchor.getBoundingClientRect();
    pop.style.left = (r.left) + "px";
    pop.style.top = (r.bottom + window.scrollY + 6) + "px";
    buildPicker(new Date(current));
    document.addEventListener("click", onDocClick, { once: true });
  }
  function onDocClick(e){
    if (pop.contains(e.target) || e.target === pickerBtn) return;
    pop.hidden = true;
  }
  function buildPicker(baseDate){
    const months = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
    let year = baseDate.getFullYear();
    let month = baseDate.getMonth();

    const atMinYear = (year <= __minYear);
    const atMaxYear = (year >= __maxYear);

    const first = new Date(year, month, 1);
    const firstDow = (first.getDay()+6)%7; // 0=Mon
    const daysInMonth = new Date(year, month+1, 0).getDate();

    let html = `<div class="picker-head">
      <button id="pkPrevY">‹</button>
      <div style="font-weight:600">${year}</div>
      <button id="pkNextY">›</button>
    </div>`;

    html += `<div class="picker-wrap">`;

    html += `<div><div class="picker-cal">`;
    const dows = ['L','M','X','J','V','S','D'];
    for(const d of dows){ html += `<div class="dow">${d}</div>`; }
    for(let i=0;i<firstDow;i++) html += `<div></div>`;
    for(let d=1; d<=daysInMonth; d++){
      html += `<button class="d" data-d="${d}">${d}</button>`;
    }
    html += `</div>
      <div style="display:none">
        <button id="pkPrevM">Mes ‹</button>
        <button id="pkToday">Hoy</button>
        <button id="pkNextM">› Mes</button>
      </div>
    </div>`;

    html += `<div class="picker-side">`;
    for(let m=0;m<12;m++){
      html += `<button class="m" data-m="${m}" ${m===month?'style="background:var(--accent);color:#08221f"':''}>${months[m]}</button>`;
    }
    html += `</div>`;

    html += `</div>`;
    pop.innerHTML = html;

    const btnPrevY = pop.querySelector("#pkPrevY");
    const btnNextY = pop.querySelector("#pkNextY");
    const btnPrevM = pop.querySelector("#pkPrevM");
    const btnNextM = pop.querySelector("#pkNextM");

    if (atMinYear) { btnPrevY.disabled = true; btnPrevY.setAttribute('aria-disabled','true'); }
    if (atMaxYear) { btnNextY.disabled = true; btnNextY.setAttribute('aria-disabled','true'); }

    btnPrevY.onclick = ()=>{ const y=year-1; if (y < __minYear) return; const d=new Date(y, month, 1); current=d; buildGrid(current); buildPicker(d); };
    btnNextY.onclick = ()=>{ const y=year+1; if (y > __maxYear) return; const d=new Date(y, month, 1); current=d; buildGrid(current); buildPicker(d); };
    btnPrevM.onclick = ()=>{ const t=new Date(year, month-1, 1); if (t.getFullYear() < __minYear) return; current=t; buildGrid(current); buildPicker(t); };
    btnNextM.onclick = ()=>{ const t=new Date(year, month+1, 1); if (t.getFullYear() > __maxYear) return; current=t; buildGrid(current); buildPicker(t); };
    pop.querySelector("#pkToday").onclick = ()=>{
      current = new Date();
      buildGrid(current);
      pop.hidden = true;
    };
    pop.querySelectorAll(".d").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const day = parseInt(btn.dataset.d,10);
        const date = new Date(year, month, day);
        current = date;
        buildGrid(current);
        pop.hidden = true;
      });
    });
    pop.querySelectorAll('.m').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        const m = parseInt(btn.dataset.m,10);
        const date = new Date(year, m, 1);
        if (date.getFullYear() < __minYear || date.getFullYear() > __maxYear) return;
        current = date;
        buildGrid(current);
        pop.hidden = true;
      });
    });
  }

  if (pickerBtn) pickerBtn.addEventListener("click", (e)=>{
    e.stopPropagation();
    if (!pop.hidden) { pop.hidden = true; return; }
    openPicker();
  });

  buildGrid(current);
})();


/* ---- Overlay de reservas (estable) ---- */
(function(){
  const grid = document.getElementById("calendarGrid");
  if (!grid) return;

  const startHour = 7;

  function pad2(n){ return n<10 ? "0"+n : ""+n; }
  function toDateStr(d){ return d.getFullYear()+"-"+pad2(d.getMonth()+1)+"-"+pad2(d.getDate()); }

  async function fetchJSON(url){
    const r = await fetch(url, {headers:{"Accept":"application/json"}});
    if (!r.ok) throw new Error("HTTP "+r.status+" @ "+url);
    return await r.json();
  }

  function getWeekStart(){
  if (window.__SNB_WEEK_START) { return new Date(window.__SNB_WEEK_START); }
  const base=(typeof current!=='undefined'&&current)?current:new Date();
  const d=new Date(base); const k=(d.getDay()+6)%7; d.setDate(d.getDate()-k); d.setHours(0,0,0,0); return d;
}

  async function renderReservations(weekStart){
    // limpiar bloques anteriores
    [...grid.querySelectorAll('.resv-block')].forEach(n=>n.remove());
    const areaSel = document.getElementById("areaSelect");
    const id_area = areaSel ? areaSel.value : null;
    if (!id_area) return;
    const data = await fetchJSON(`/api/calendario/semana?id_area=${encodeURIComponent(id_area)}&start=${toDateStr(weekStart)}`);
    const rowBase = 2;
    for(const r of data){
      let f;
      const _fstr = String(r.fecha);
      if (/^\d{4}-\d{2}-\d{2}$/.test(_fstr)) {
        const parts = _fstr.split('-').map(Number);
        f = new Date(parts[0], (parts[1]||1)-1, parts[2]||1);
        f.setHours(0,0,0,0);
      } else {
        // fallback (RFC 1123, ISO con 'T', etc.)
        const _tmp = new Date(_fstr);
        f = new Date(_tmp.getUTCFullYear(), _tmp.getUTCMonth(), _tmp.getUTCDate());
      }
      const d0 = new Date(weekStart); d0.setHours(0,0,0,0);
      const dayIdx = (f.getDay()+6)%7;
      if (dayIdx < 0 || dayIdx > 6) continue;
      const [h1] = r.ini.split(":").map(Number);
      const [h2] = r.fin.split(":").map(Number);
      const startRow = rowBase + (h1 - startHour);
      const endRow   = rowBase + (h2 - startHour);

      const div = document.createElement("div");
      div.className = "resv-block" + (r.estado==0 ? " is-pend" : " is-conf");
      div.style.gridColumn = (dayIdx+2) + " / " + (dayIdx+3);
      div.style.gridRow = startRow + " / " + endRow;
      div.dataset.id = r.id_reserva;
      div.dataset.fecha = r.fecha;
      div.dataset.ini = r.ini;
      div.dataset.fin = r.fin;
      div.title = `${r.ini} – ${r.fin}`;

      const estadoTxt = (window.SNB_USER_ROLE_ID===2 ? "Reservada" : (r.estado==0 ? "Pend." : "Conf."));
      const torreTxt = (r.torre!=null ? "T"+r.torre : "");
      const aptoTxt = (r.apartamento!=null ? " Apto "+r.apartamento : "");
      div.innerHTML = `<div class="resv-title" title="${(`${r.nombre || ""} ${r.apellido || ""}`).trim()}">${(`${r.nombre || ""} ${r.apellido || ""}`).trim()}</div>
                       <div class="resv-sub">${torreTxt}${aptoTxt} • ${estadoTxt}</div>`;

      // --- Ajuste adaptativo del nombre (umbral por altura del bloque) ---
      (function(){
        const titleEl = div.querySelector(".resv-title");
        const subEl = div.querySelector(".resv-sub");
        if (!titleEl || !subEl) return;
        const totalH = div.clientHeight || 0;

        // Forzar reglas base en línea para ganar a cualquier CSS previo
        titleEl.style.overflow = "hidden";
        titleEl.style.textOverflow = "ellipsis";

        // Umbrales (px) para permitir más líneas sin cambiar el alto del bloque
        // ~44px: 1 línea (por defecto)
        // >= 64px: 2 líneas
        // >= 84px: 3 líneas (máximo)
        let lines = 1;
        if (totalH >= 84) lines = 3;
        else if (totalH >= 64) lines = 2;

        if (lines === 1){
          titleEl.style.whiteSpace = "nowrap";
          titleEl.style.display = "block";
          titleEl.style.webkitLineClamp = null;
          titleEl.style.webkitBoxOrient = null;
        } else {
          titleEl.style.whiteSpace = "normal";
          titleEl.style.display = "-webkit-box";
          titleEl.style.webkitBoxOrient = "vertical";
          titleEl.style.webkitLineClamp = String(lines);
        }
      })();
grid.appendChild(div);
      if (window.SNB_USER_ROLE_ID===4){ div.addEventListener("dblclick", ()=> openResvInfo(div)); } else if (window.SNB_USER_ROLE_ID!==2) { div.addEventListener("dblclick", ()=> openResvActions(div)); } }
  }

  function ensureGridThenPaint(){
    const ws = getWeekStart();
    // Si el grid aún no está construido, lo construimos para esta semana visible
    if (grid.children.length < 10){
      // buildGrid acepta cualquier fecha; usamos el inicio de la semana actual (ws)
      if (typeof buildGrid === 'function') buildGrid(ws);
      requestAnimationFrame(()=> renderReservations(ws));
    }else{
      renderReservations(ws);
    }
  }

  // Exponer para repintar tras edición
  window.renderReservations = renderReservations;

  document.getElementById("prevWeek")?.addEventListener("click", ()=> setTimeout(ensureGridThenPaint,0));
  document.getElementById("nextWeek")?.addEventListener("click", ()=> setTimeout(ensureGridThenPaint,0));
  document.getElementById("todayBtn")?.addEventListener("click", ()=> setTimeout(ensureGridThenPaint,0));
  document.getElementById("areaSelect")?.addEventListener("change", ()=> setTimeout(ensureGridThenPaint,0));
  window.addEventListener("load", ()=> setTimeout(ensureGridThenPaint,0));

  // ---- Modal Acciones (local, centrado en calendario) ----
  function ensureResvLocalModal(){
    const wrap = document.getElementById("calendarWrapper") || document.body;
    let m = document.getElementById("resvActionModal");
    if (m && m.parentElement !== wrap){ m.remove(); m = null; }
    if (!m){
      m = document.createElement("div");
      m.className = "modal"; m.id = "resvActionModal";
      m.style.position="absolute"; m.style.inset="0"; m.style.display="none";
      m.style.alignItems="center"; m.style.justifyContent="center";
      m.style.background="rgba(12,53,47,.60)";
      m.innerHTML = `<div class="modal-content" style="max-width:480px">
        <div class="modal-head"><h3 style="margin:0">Acciones de la reserva</h3>
          <button id="resvClose" class="btn-icon">×</button></div>
        <div class="modal-body" id="resvBody" style="margin-bottom:12px;color:var(--text)"></div>
        <div class="modal-actions" style="display:flex;gap:8px;justify-content:flex-end">
          <button id="btnEditResv" class="btn">Editar</button>
          <button id="btnConfirmResv" class="btn btn-blue">Confirmar</button>
          <button id="btnDeleteResv" class="btn btn-red">Eliminar</button>
        </div>
      </div>`;
      wrap.appendChild(m);
      m.addEventListener("click", (e)=>{ if(e.target===m) closeResvModal(); });
      m.querySelector("#resvClose").addEventListener("click", ()=> closeResvModal());
    }
    return m;
  }
  function closeResvModal(){
    const m = document.getElementById("resvActionModal");
    if (m){ m.style.display="none"; m.setAttribute("hidden",""); m.setAttribute("aria-hidden","true"); }
  }
  function openResvActions(block){
    const m = ensureResvLocalModal();
    window._snbCurrentBlock = block;
    const bodyTxt = block.querySelector(".resv-title").textContent + " • " + block.querySelector(".resv-sub").textContent;
    document.getElementById("resvBody").textContent = bodyTxt;
    m.style.display="flex"; m.removeAttribute("hidden"); m.setAttribute("aria-hidden","false");

    const onConfirm = async ()=>{
      const id = block.dataset.id;
      const r = await fetch(`/api/reservas/${id}/confirmar`, {method:"POST", headers:{"Accept":"application/json"}}).then(r=>r.json());
      if (r.ok){
        block.classList.remove("is-pend"); block.classList.add("is-conf");
        const sub = block.querySelector(".resv-sub"); if (sub) sub.textContent = sub.textContent.replace("Pend.", "Conf.");
        if (typeof snBlueToast==='function') snBlueToast("Reserva confirmada.");
      }
      closeResvModal();
    };
    const onDelete = async ()=>{
      const id = block.dataset.id;
      const r = await fetch(`/api/reservas/${id}/eliminar`, {method:"POST", headers:{"Accept":"application/json"}}).then(r=>r.json());
      if (r.ok){ block.remove(); if (typeof snBlueToast==='function') snBlueToast("Reserva eliminada."); }
      closeResvModal();
    };
    const b1 = document.getElementById("btnConfirmResv");
    const b2 = document.getElementById("btnDeleteResv");
    if (b1) b1.onclick = onConfirm;
    if (b2) b2.onclick = onDelete;

    const bEdit = document.getElementById("btnEditResv");
    if (bEdit){ bEdit.onclick = (ev)=>{ ev.preventDefault(); closeResvModal(); openResvEdit(block); }; }
    // delegación fallback
    if (m._editDelegation) m.removeEventListener("click", m._editDelegation, true);
    m._editDelegation = (ev)=>{ if (ev.target && ev.target.id==='btnEditResv'){ ev.preventDefault(); closeResvModal(); openResvEdit(block); } };
    m.addEventListener("click", m._editDelegation, true);
  }

  // ---- Modal Editar (igual a Nueva Reservación) ----
  async function _snbLoadAreaMeta(id_area){
    const r = await fetch(`/api/area_meta?id_area=${encodeURIComponent(id_area)}`, {headers:{"Accept":"application/json"}});
    if (!r.ok) return {horas:1, horas_inicio:[]};
    return await r.json();
  }
  async function _snbLoadOcupadas(id_area, fecha){
    const r = await fetch(`/api/reservas/ocupadas?id_area=${encodeURIComponent(id_area)}&fecha=${encodeURIComponent(fecha)}`, {headers:{"Accept":"application/json"}});
    if (!r.ok) return [];
    return await r.json();
  }
  function _snbAddHours(hhmm, hours){
    const [h,m] = hhmm.split(':').map(x=>parseInt(x,10));
    const d = new Date(2000,0,1,h,m||0); d.setHours(d.getHours()+(parseInt(hours,10)||0));
    return (d.getHours()<10?'0':'')+d.getHours()+":"+(d.getMinutes()<10?'0':'')+d.getMinutes();
  }

  function ensureResvEditModal(){
    const wrap = document.getElementById("calendarWrapper") || document.body;
    let m = document.getElementById("resvEditModal");
    if (m && m.parentElement !== wrap){ m.remove(); m = null; }
    if (!m){
      m = document.createElement("div");
      m.className="modal"; m.id="resvEditModal";
      m.style.position="absolute"; m.style.inset="0"; m.style.display="none";
      m.style.alignItems="center"; m.style.justifyContent="center";
      m.style.background="rgba(12,53,47,.60)";
      m.innerHTML = `<div class="modal-content" style="max-width:720px">
        <div class="modal-head">
          <h3 class="form-title" style="margin:0">Editar reservación</h3>
          <button id="resvEditClose" class="btn-icon">×</button>
        </div>
        <div class="form-grid" style="gap:12px">
          <div class="form-row"><label class="lbl">Área</label><input id="editAreaName" class="input" type="text" readonly></div>
          <div class="form-row"><label class="lbl">Fecha</label><input type="date" id="editFecha" class="input"></div>
          <div class="form-row"><label class="lbl">Hora de inicio</label><div id="editHorasGrid" class="horas-grid"></div></div>
          <div class="form-row"><label class="lbl">Hora fin</label><input id="editHoraFin" class="input" type="text" readonly></div>
          <div class="form-actions"><button id="btnEditCancelar" class="btn">Cancelar</button><button id="btnEditGuardar" class="btn btn-blue">Guardar</button></div>
        </div>
      </div>`;
      wrap.appendChild(m);
      m.addEventListener("click", (e)=>{ if(e.target===m) closeResvEditModal(); });
      m.querySelector("#resvEditClose").addEventListener("click", ()=> closeResvEditModal());
      m.querySelector("#btnEditCancelar").addEventListener("click", ()=> closeResvEditModal());
    }
    return m;
  }
  function closeResvEditModal(){
    const m = document.getElementById("resvEditModal");
    if (m){ m.style.display="none"; m.setAttribute("hidden",""); m.setAttribute("aria-hidden","true"); }
  }
  async function openResvEdit(block){
    const m = ensureResvEditModal();
    const areaSel = document.getElementById("areaSelect");
    const id_area = areaSel ? areaSel.value : null;
    const areaInput = m.querySelector("#editAreaName");
    if (areaInput && areaSel){ const opt = areaSel.options[areaSel.selectedIndex]; areaInput.value = opt ? opt.text : ""; }
    const f = m.querySelector("#editFecha");
    const horasGrid = m.querySelector("#editHorasGrid");
    const finOut = m.querySelector("#editHoraFin");

    // Prefill fecha/hora actual
    if (f) f.value = (block.dataset.fecha || "").substring(0,10);

    // Cargar metadatos área y construir horas
    let durHours = 1;
    async function buildHours(){
// Construye las horas una sola vez por clave (area|fecha) y sin duplicados
const key = `${id_area}|${f.value || ''}`;
if (horasGrid.dataset.key === key) { return; }
horasGrid.dataset.key = key;

horasGrid.innerHTML = "";
const meta = await _snbLoadAreaMeta(id_area);
durHours = meta.horas || 1;

const base = (meta.horas_inicio && meta.horas_inicio.length)
  ? meta.horas_inicio
  : ((meta.horarios && meta.horarios.length)
      ? meta.horarios
      : Array.from({length:15}, (_,i)=> (i+7).toString().padStart(2,'0')+':00'));

// 🔒 sin duplicados
const lista = Array.from(new Set(base));

const fechaStr = f.value || (block.dataset.fecha || '').substring(0,10);
const ocupadas = await _snbLoadOcupadas(id_area, fechaStr);

for (const hh of lista){
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'hora-pill';
  b.textContent = hh;
  b.dataset.val = hh;
  if (ocupadas.includes(hh)) b.classList.add('disabled');
  b.addEventListener('click', ()=>{
    if (b.classList.contains('disabled')) return;
    horasGrid.querySelectorAll('.hora-pill').forEach(x=>x.classList.remove('selected'));
    b.classList.add('selected');
    if (finOut) finOut.value = _snbAddHours(hh, durHours);
  });
  horasGrid.appendChild(b);
}

// Seleccionar hora actual si está disponible
const cur = block.dataset.ini || '07:00';
const btn = horasGrid.querySelector(`.hora-pill[data-val="${cur}"]`);
if (btn && !btn.classList.contains('disabled')){
  btn.classList.add('selected');
  if (finOut) finOut.value = _snbAddHours(cur, durHours);
} else {
  if (finOut) finOut.value = '';
}
}
    if (f && !f.value) f.value = (block.dataset.fecha || "").substring(0,10);
    await buildHours();
    if (f){ f.addEventListener("change", async ()=>{ await buildHours(); }); }

    // Abrir modal
    m.style.display="flex"; m.removeAttribute("hidden"); m.setAttribute("aria-hidden","false");

    // Guardar
    const save = m.querySelector("#btnEditGuardar");
    save.onclick = async ()=>{
      // Validación +1 año
      const today = new Date(); const limit = new Date(today.getFullYear()+1, today.getMonth(), today.getDate());
      const parts = (f.value||"").split("-"); let fDate=null;
      if (parts.length===3) fDate = new Date(parseInt(parts[0]), parseInt(parts[1])-1, parseInt(parts[2]));
      if (fDate && fDate > limit){ if (typeof snBlueToast==='function') snBlueToast("La fecha no puede ser mayor a 1 año desde hoy."); return; }
      const sel = horasGrid.querySelector(".hora-pill.selected"); const hora_inicio = sel ? sel.dataset.val : (block.dataset.ini||"07:00");
      const id = block.dataset.id;
      const r = await fetch(`/api/reservas/${id}/editar`, {method:"POST", headers:{"Accept":"application/json","Content-Type":"application/x-www-form-urlencoded"}, body:new URLSearchParams({fecha:f.value, hora_inicio})}).then(r=>r.json());
      if (r && r.ok){
        closeResvEditModal();
        if (typeof snBlueToast==='function') snBlueToast("Reserva actualizada.");
        // repintar
        const ws = new Date(f.value); ws.setDate(ws.getDate() - ((ws.getDay()+6)%7)); ws.setHours(0,0,0,0);
        renderReservations(ws);
      }else{
        alert(r.error || "No se pudo actualizar.");
      }
    };
  }
})();


// --- Toast azul simple ---
function snBlueToast(text){
  let css = document.getElementById("sn-toast-styles");
  if(!css){
    css = document.createElement("style"); css.id="sn-toast-styles";
    css.textContent = `#sn-toast{position:fixed;top:18px;right:24px;z-index:2147483647;}
.sn-toast{display:flex;align-items:center;gap:10px;background:#1e88e5;color:#fff;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.25);padding:12px 16px;min-width:260px;opacity:0;transform:translateY(-8px);transition:opacity .25s,transform .25s;}
.sn-toast.show{opacity:1;transform:translateY(0)} .sn-close{background:transparent;border:0;color:#fff;margin-left:8px;}`;
    document.head.appendChild(css);
    const c = document.createElement("div"); c.id="sn-toast"; document.body.appendChild(c);
  }
  const c = document.getElementById("sn-toast");
  const t = document.createElement("div"); t.className="sn-toast"; t.innerHTML = `<span>${text}</span><button class="sn-close">×</button>`;
  t.querySelector(".sn-close").onclick = ()=> t.remove(); c.appendChild(t); requestAnimationFrame(()=> t.classList.add("show"));
  setTimeout(()=>{ t.classList.remove("show"); setTimeout(()=>t.remove(),300); }, 3500);
}

// Modal solo-información para rol VISOR (3)
function openResvInfo(block){
  // crear overlay ligero si no existe
  let ov = document.getElementById("resvInfoOverlay");
  if (!ov){
    ov = document.createElement("div");
    ov.id = "resvInfoOverlay";
    ov.style.position="fixed"; ov.style.inset="0"; ov.style.background="rgba(0,0,0,.35)"; ov.style.zIndex="9999";
    ov.innerHTML = '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:#0e3a36;border:1px solid rgba(255,255,255,.08);box-shadow:0 10px 24px rgba(0,0,0,.35);border-radius:14px;padding:16px 18px;min-width:340px;max-width:520px;color:#fff;">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;"><h3 style="margin:0;font-size:18px;">Detalle de la reserva</h3><button id="riClose" style="background:transparent;border:0;color:#fff;font-size:18px;cursor:pointer;">×</button></div>'
      + '<div id="riBody" style="font-size:14px;line-height:1.4;"></div>'
      + '<div style="margin-top:12px;display:flex;justify-content:flex-end;"><button id="riOk" class="btn-compact">Cerrar</button></div>'
      + '</div>';
    document.body.appendChild(ov);
    ov.addEventListener("click", (e)=>{ if (e.target===ov) ov.remove(); });
    ov.querySelector("#riClose").onclick = ()=> ov.remove();
    ov.querySelector("#riOk").onclick = ()=> ov.remove();
  }
  const nombre = block.querySelector(".resv-title")?.getAttribute("title") || block.querySelector(".resv-title")?.textContent || "";
  const sub = block.querySelector(".resv-sub")?.textContent || "";
  const ini = block.dataset.ini || "";
  const fin = block.dataset.fin || "";
  const fecha = block.dataset.fecha || "";
  const body = document.getElementById("riBody");
  body.innerHTML = `<p style="margin:0 0 6px 0;"><b>${nombre}</b></p><p style="margin:0 0 6px 0;">${sub}</p><p style="margin:0;">${fecha} — ${ini} a ${fin}</p>`;
  document.getElementById("resvInfoOverlay").style.display="block";
}

// Toggle menú de usuario (flecha con opciones)
(function(){
  var menu = document.querySelector(".user-menu");
  if (!menu) return;
  var toggle = menu.querySelector(".user-menu-toggle");
  var dropdown = menu.querySelector(".user-menu-dropdown");
  if (!toggle || !dropdown) return;

  toggle.addEventListener("click", function(ev){
    ev.stopPropagation();
    menu.classList.toggle("open");
  });

  document.addEventListener("click", function(){
    menu.classList.remove("open");
  });
})();
