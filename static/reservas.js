
(function(){
  const fechaEl = document.getElementById("fecha");
  const areaEl = document.getElementById("id_area");
  const horasWrap = document.getElementById("horasDisponibles");
  const horaInicioEl = document.getElementById("hora_inicio");
  const horaFinAuto = document.getElementById("horaFinAuto");
  const horaFinWrap = document.getElementById("horaFinWrap");
  const fechaHelp = document.getElementById("fechaHelp");
  const priceInfo = document.getElementById("priceInfo");

  
  async function fetchJSON(url){
    const r = await fetch(url, {
      headers: { "Accept":"application/json" },
      credentials: "same-origin" // importante: envía cookies de sesión
    });
    const ct = (r.headers.get("content-type") || "").toLowerCase();
    if (!ct.includes("application/json")){
      throw new Error("Respuesta no-JSON (posible sesión expirada o redirección)");
    }
    if (!r.ok) throw new Error("HTTP "+r.status+" @ "+url);
    return await r.json();
  }
  function toHHMM(d){
    const hh = String(d.getHours()).padStart(2,'0');
    const mm = String(d.getMinutes()).padStart(2,'0');
    return `${hh}:${mm}`;
  }
  async function getAreaMeta(id_area){
    // 1) Try RESTful route (/api/areas/<id>/meta), fallback to /api/area_meta?id_area=..
    try{
      return await fetchJSON(`/api/areas/${encodeURIComponent(id_area)}/meta`);
    }catch(e){
      // fallback
      return await fetchJSON(`/api/area_meta?id_area=${encodeURIComponent(id_area)}`);
    }
  }

  async function renderHoras(){
    if (!horasWrap || !areaEl) return;
    horasWrap.innerHTML = "";
    if (horaInicioEl) horaInicioEl.value = "";
    if (horaFinAuto) horaFinAuto.textContent = "";
    if (horaFinWrap) horaFinWrap.innerHTML = "";

    const id_area = areaEl.value;
    const fecha = fechaEl ? fechaEl.value : "";

    if (!id_area){
      if (fechaHelp) fechaHelp.textContent = "Selecciona un área social.";
      return;
    }

    try{
      const meta = await getAreaMeta(id_area);
      if (priceInfo){
        const durH = Number(meta.horas)||0;
        const precioNum = Number(meta.precio||0);
        if (durH>0 && !isNaN(precioNum)){
          priceInfo.textContent = `Precio por ${durH} horas Q${precioNum.toFixed(2)}`;
        }else{
          priceInfo.textContent = '';
        }
      }
      const dur = Number(meta.horas) || 0;
      const inicios = Array.isArray(meta.horas_inicio) && meta.horas_inicio.length ? meta.horas_inicio
                        : (Array.isArray(meta.horarios) ? meta.horarios : []);

      let ocupadas = [];
      if (fecha){ // solo consultamos ocupadas si ya hay fecha
        try{
          ocupadas = await fetchJSON(`/api/reservas/ocupadas?id_area=${encodeURIComponent(id_area)}&fecha=${encodeURIComponent(fecha)}`);
          if (fechaHelp) fechaHelp.textContent = "";
        }catch(_e){
          ocupadas = [];
        }
      }else{
        if (fechaHelp) fechaHelp.textContent = "Selecciona la fecha para validar ocupadas.";
      }

      inicios.forEach(h => {
        const taken = fecha ? ocupadas.includes(h) : false;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "hora-pill" + (taken ? " disabled" : "");
        btn.textContent = h;
        btn.disabled = taken;
        btn.addEventListener("click", () => {
          document.querySelectorAll(".hora-pill.selected").forEach(x=>x.classList.remove("selected"));
          btn.classList.add("selected");
          if (horaInicioEl) horaInicioEl.value = h;

          const [HH,MM] = h.split(":").map(Number);
          const dt = new Date(0,0,0,HH||0,MM||0);
          dt.setHours(dt.getHours() + dur);
          const finTxt = toHHMM(dt);
          if (horaFinWrap){
            horaFinWrap.innerHTML = "";
            const finBtn = document.createElement('span');
            finBtn.className = 'hora-pill selected disabled';
            finBtn.textContent = finTxt;
            finBtn.setAttribute('aria-label','Hora fin');
            horaFinWrap.appendChild(finBtn);
          } else if (horaFinAuto) {
            horaFinAuto.textContent = "Hora fin: " + finTxt;
          }
        });
        horasWrap.appendChild(btn);
      });

      // Si no hay horarios, mostrar mensaje
      if (!inicios.length){
        const p = document.createElement("div");
        p.className = "muted";
        p.textContent = "No hay horas configuradas para esta área.";
        horasWrap.appendChild(p);
      }
    }catch(err){
      console.error("renderHoras error:", err);
      if (fechaHelp) fechaHelp.textContent = "No se pudieron cargar las horas. Recarga e intenta de nuevo.";
    }
  }

  if (areaEl) areaEl.addEventListener("change", renderHoras);
  if (fechaEl) fechaEl.addEventListener("change", renderHoras);
  window.addEventListener("DOMContentLoaded", renderHoras);

  // ---- Modal Buscar Residente ----
  const modal = document.getElementById("modalUsuarios");
  const abrir = document.getElementById("btnCambiarUsuario");
  const cerrar = document.getElementById("cerrarModal");
  const filtro = document.getElementById("filtro");
  const resultados = document.getElementById("resultados");
  const idUsuario = document.getElementById("id_usuario");
  const usuarioDisplay = document.getElementById("usuarioDisplay");

  function openModal(){
    if (!modal) return;
    modal.hidden = false; modal.classList.add("show");
    if (filtro){ filtro.value=""; filtro.focus(); }
    if (resultados){ resultados.innerHTML = ""; }
  }
  function closeModal(){
    if (!modal) return;
    modal.hidden = true; modal.classList.remove("show");
  }
  async function buscar(q){
    const url = `/api/usuarios?q=${encodeURIComponent(q||"")}`;
    const data = await fetchJSON(url);
    resultados.innerHTML = data.map(u=>`
      <div class="usuario-item" data-id="${u.id_usuario}" style="padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.06);cursor:pointer">
        <div class="u-name"><strong>${u.nombre} ${u.apellido}</strong></div>
        <div class="u-sub muted">Torre ${u.torre || '-'} • Apt. ${u.apartamento || '-'} • ${u.celular || ''}</div>
      </div>
    `).join("");
    resultados.querySelectorAll(".usuario-item").forEach(el=>{
      el.addEventListener("click", ()=>{
        const id = el.dataset.id;
        if (idUsuario) idUsuario.value = id;
        if (usuarioDisplay){
          const name = el.querySelector(".u-name").textContent;
          const sub = el.querySelector(".u-sub").textContent;
          usuarioDisplay.innerHTML = `<strong>${name}</strong><div class="muted" style="font-weight:400">${sub}</div>`;
        }
        closeModal();
      });
    });
  }

  if (abrir) abrir.addEventListener("click", openModal);
  if (cerrar) cerrar.addEventListener("click", closeModal);
  if (modal) modal.addEventListener("click", (e)=>{ if (e.target === modal) closeModal(); });
  if (filtro){
    let t; 
    filtro.addEventListener("input", e=>{
      clearTimeout(t);
      t = setTimeout(()=> buscar(e.target.value), 250);
    });
    // primer fetch vacío
    buscar("");
  }

})();
