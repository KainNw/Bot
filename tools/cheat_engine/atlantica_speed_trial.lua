-- Atlantica: manual, ten-second Cheat Engine timer experiment.
-- Requires 64-bit Cheat Engine on Windows; the game itself is 32-bit.
-- Loading this file only opens the form. Only its Test button changes timers.
local M = {version = "0.17.0", rates = {1.25, 1.5, 2, 3, 4}}

local function equalRate(a, b)
  return type(a) == "number" and math.abs(a - b) < 0.0001
end

-- The controller also runs against a fake adapter in the regression tests.
function M.newTrial(api)
  local t = {phase = "idle", message = "Sin cambios de velocidad.", binding = nil,
    ownsChange = false, history = {}, reportedRate = nil, busy = false, stopRequested = nil}

  function t.note(message)
    t.message = message
    t.history[#t.history + 1] = tostring(api.now()) .. " ms | " .. message
    if #t.history > 100 then table.remove(t.history, 1) end
  end

  function t.release()
    if t.binding then api.release(t.binding); t.binding = nil end
  end

  local function restoreNow(reason)
    if not t.ownsChange then
      t.release()
      t.phase = "idle"
      t.note(reason .. "; no había cambio de temporizadores pendiente.")
      return true
    end
    t.phase = "restoring"
    local ok, result = pcall(function()
      if not api.returnToOriginal(t.binding) then return "exited" end
      api.setRate(t.binding, 1)
      t.reportedRate = api.reportedRate()
      if not equalRate(t.reportedRate, 1) then error("CE no informa 1×.") end
      return "reported"
    end)
    if not ok then
      t.phase = "restore_failed"
      t.note("Restauración pendiente: " .. tostring(result) .. " Pulsa Restaurar 1×.")
      return false
    end
    t.ownsChange = false
    t.phase = "idle"
    t.release()
    t.note(reason .. (result == "exited" and "; la instancia terminó." or
      "; CE informa 1×. Comprueba el juego; esto no mide la animación."))
    return true
  end

  local function finishRestore(reason)
    local ok, result = pcall(restoreNow, reason)
    if not ok then
      t.phase = "restore_failed"
      t.note("Limpieza pendiente: " .. tostring(result))
      return false
    end
    return result
  end

  function t.restore(reason)
    -- CE may pump GUI messages while injecting/loading symbols. A timer,
    -- close event, or Stop click must not start another nested speed request.
    if t.busy then t.stopRequested = reason; return false end
    t.busy = true
    local result = finishRestore(reason)
    t.stopRequested, t.busy = nil, false
    return result
  end

  function t.start(rate)
    if t.busy then error("CE todavía está procesando la prueba.") end
    if t.binding or t.ownsChange then error("Termina o restaura la prueba anterior.") end
    local allowed = false
    for _, value in ipairs(M.rates) do if rate == value then allowed = true end end
    if not allowed then error("Elige una de las velocidades de prueba.") end
    t.busy = true
    local ok, err = pcall(function()
      t.binding = api.bind()
      if not equalRate(api.reportedRate(), 1) then
        error("CE ya informa otra velocidad. Vuelve a 1× antes de probar.")
      end
      t.battle = api.observe(t.binding)
      t.rate, t.armedAt = rate, api.now()
      t.phase = "arming"
      t.note("PID " .. t.binding.pid .. ", creación " .. t.binding.created ..
        ": comprobando combate antes de aplicar " .. rate .. "×.")
    end)
    if not ok then
      finishRestore(tostring(err))
      t.stopRequested, t.busy = nil, false
      return false
    end
    t.busy = false
    if t.stopRequested then
      local reason = t.stopRequested
      t.stopRequested = nil
      t.restore(reason)
      return false
    end
    return true
  end

  function t.tick()
    if t.busy then return end
    if t.phase ~= "arming" and t.phase ~= "active" then return end
    t.busy = true
    local ok, err = pcall(function()
      local current = api.observe(t.binding)
      if current ~= t.battle then error("El combate cambió.") end
      if t.phase == "arming" then
        if api.now() - t.armedAt < 200 then return end
        if not equalRate(api.reportedRate(), 1) then error("La velocidad de CE cambió.") end
        -- Retain ownership even if CE fails after partially installing its hooks.
        t.ownsChange = true
        t.deadline = api.now() + 10000
        t.phase = "applying"
        api.setRate(t.binding, t.rate)
        t.reportedRate = api.reportedRate()
        if not equalRate(t.reportedRate, t.rate) then error("CE no informa el factor solicitado.") end
        if api.now() >= t.deadline then finishRestore("Plazo cumplido durante la carga de CE"); return end
        if api.observe(t.binding) ~= t.battle then error("El combate cambió durante la aplicación.") end
        t.phase = "active"
        t.note("CE informa " .. t.rate .. "× en PID " .. t.binding.pid ..
          ". Ejecuta una magia manual; prueba de hasta 10 s.")
      elseif api.now() >= t.deadline then
        finishRestore("Plazo de 10 s cumplido")
      elseif not equalRate(api.reportedRate(), t.rate) then
        error("La velocidad de CE cambió durante la prueba.")
      end
    end)
    if not ok then finishRestore(tostring(err)) end
    if t.stopRequested and t.binding then finishRestore(t.stopRequested) end
    t.stopRequested, t.busy = nil, false
  end

  function t.close()
    return t.restore("Prueba cerrada")
  end

  return t
end

function M.newCEAdapter()
  assert(cheatEngineIs64Bit(), "Abre Cheat Engine de 64 bits en Windows.")
  local buffer = createMemoryStream()
  buffer.Size = 32
  local addresses = {}
  for _, name in ipairs({"OpenProcess", "GetProcessTimes", "GetProcessId",
      "WaitForSingleObject", "CloseHandle", "CreateMutexW", "ReleaseMutex"}) do
    addresses[name] = getAddress("kernel32." .. name, true)
    assert(addresses[name] and addresses[name] ~= 0, "Falta la API local " .. name)
  end
  local function win(name, ...)
    local result = executeCodeLocalEx(addresses[name], ...)
    assert(type(result) == "number", "Falló la API local " .. name)
    return result
  end
  local function creation(handle)
    assert(win("GetProcessTimes", handle, buffer.Memory, buffer.Memory + 8,
      buffer.Memory + 16, buffer.Memory + 24) ~= 0, "No se pudo leer la creación del proceso.")
    local lo, hi = readIntegerLocal(buffer.Memory), readIntegerLocal(buffer.Memory + 4)
    assert(lo and hi, "No se pudo leer FILETIME.")
    return string.format("%08X%08X", hi & 0xffffffff, lo & 0xffffffff)
  end
  local function read32(address)
    local value = readInteger(address)
    assert(type(value) == "number", "Lectura no disponible: " .. string.format("%08X", address))
    return value & 0xffffffff
  end
  local function pointer(address)
    local value = read32(address)
    assert(value >= 0x10000 and value <= 0xffff0000, "Puntero transitorio del cliente.")
    return value
  end
  local function identity(b)
    assert(getOpenedProcessID() == b.pid, "CE cambió de PID.")
    local handle = getOpenedProcessHandle()
    assert(handle and handle ~= 0 and win("GetProcessId", handle) == b.pid,
      "El handle de CE no corresponde al PID.")
    assert(creation(handle) == b.created and creation(b.handle) == b.created,
      "La instancia del proceso cambió.")
    assert(win("WaitForSingleObject", b.handle, 0) == 0x102, "La instancia terminó.")
  end
  local api = {now = getTickCount, reportedRate = speedhack_getSpeed}
  function api.release(b)
    if b.mutex then win("ReleaseMutex", b.mutex); win("CloseHandle", b.mutex); b.mutex = nil end
    if b.handle then win("CloseHandle", b.handle); b.handle = nil end
  end
  function api.bind()
    local b = {pid = getOpenedProcessID()}
    assert(type(b.pid) == "number" and b.pid > 0, "Selecciona el PID del juego en CE.")
    local ok, err = pcall(function()
      -- QUERY_LIMITED_INFORMATION | SYNCHRONIZE. Keep the original instance alive
      -- as a kernel object, independently of CE changing its selected process.
      b.handle = win("OpenProcess", 0x101000, 0, b.pid)
      assert(b.handle ~= 0, "No se pudo abrir el proceso elegido.")
      b.created = creation(b.handle)
      identity(b)
      assert(not targetIs64Bit(), "El cliente admitido es de 32 bits.")
      local executable
      for _, module in ipairs(enumModules(b.pid) or {}) do
        if module.Name:lower() == "atlantica.exe" and module.Address == 0x400000
          and module.Is64Bit == false then executable = module.PathToFile end
      end
      assert(executable, "El PID no contiene el Atlantica.exe admitido.")
      assert(md5file(executable):lower() == "a5267787d5dc3f1699a3500d04129020",
        "La compilación del cliente no coincide.")
      b.marker = executable:match("^(.*[\\/])") .. "HuntingMode.txt"
      local expected = "8b811803000085c07d0432c0eb258b8904020000ff742404518b0d0c29a904" ..
        "8b891c0900008b4c8108e808cb0c003c010f95c0c20400"
      local anchor = readBytes(0x00431769, #expected // 2, true)
      local hex = {}
      for _, byte in ipairs(anchor or {}) do hex[#hex + 1] = string.format("%02x", byte) end
      assert(table.concat(hex) == expected, "La ruta de combate cargada no coincide.")
      local mutex = win("CreateMutexW", 0, 0,
        {type = 4, value = "Local\\AtlanticaPanel.Bot." .. b.pid})
      assert(mutex ~= 0, "No se pudo reservar el PID.")
      local result = win("WaitForSingleObject", mutex, 0)
      if result ~= 0 and result ~= 0x80 then
        win("CloseHandle", mutex)
        error("Detén el bot y las otras pruebas de ese PID antes de continuar.")
      end
      b.mutex = mutex
      identity(b)
    end)
    if not ok then api.release(b); error(err) end
    return b
  end
  function api.observe(b)
    identity(b)
    assert(not fileExists(b.marker), "Desactiva HuntingMode.txt antes de probar.")
    local function snapshot()
      local owner = pointer(0x04a9290c)
      assert(read32(owner + 0xb98) == 2, "Escena no disponible.")
      local auto = readBytes(owner + 0x16394, 1)
      local hunting = readBytes(0x04e52c5a, 1)
      assert(auto == 0 and hunting == 0, "Apaga Auto Battle y la caza nativa.")
      local world = pointer(owner + 0x828)
      local actor = pointer(world + 0x2c)
      assert(read32(actor + 0x200) == 1 and read32(actor + 0x2c) == world,
        "El personaje local cambió.")
      local index = read32(actor + 0x318)
      assert(index < 128 and read32(actor + 0x254) == 0xffffffff,
        "La prueba requiere un combate normal activo.")
      local manager = pointer(owner + 0x91c)
      assert(read32(manager) == 0x042d8aa4 and read32(manager + 0x234c) == 3,
        "El gestor todavía no está en combate.")
      local context = pointer(manager + 8 + index * 4)
      assert(read32(context + 0x6c74) ~= 0xffffffff and read32(0x1539ce18) == 1,
        "El combate todavía no está listo.")
      local key = {owner, world, actor, manager, context, index,
        read32(actor + 0x204), read32(actor + 0x208), read32(actor + 0x20c)}
      return table.concat(key, ":")
    end
    local before, after = snapshot(), snapshot()
    assert(before == after, "Los objetos del combate cambiaron durante la lectura.")
    identity(b)
    return after
  end
  function api.setRate(b, rate)
    identity(b)
    if rate ~= 1 then api.observe(b) end
    -- CE owns injection/hooking; no guessed offsets or private DLLs are used.
    speedhack_setSpeed(rate)
    identity(b)
  end
  function api.returnToOriginal(b)
    local alive = win("WaitForSingleObject", b.handle, 0)
    if alive == 0 then return false end
    assert(alive == 0x102 and creation(b.handle) == b.created,
      "No se pudo comprobar la instancia original para restaurar.")
    local selectedOk, selectedCreation = pcall(function()
      if getOpenedProcessID() ~= b.pid then return nil end
      local handle = getOpenedProcessHandle()
      if not handle or handle == 0 or win("GetProcessId", handle) ~= b.pid then return nil end
      return creation(handle)
    end)
    if not selectedOk or selectedCreation ~= b.created then
      -- Modal UI blocks normal process selection. If another script changes it,
      -- return to our still-live instance before requesting 1x. Never scale the
      -- newly selected process, nor reopen a recycled PID.
      assert(openProcess(b.pid), "Vuelve al PID original para restaurar 1×.")
    end
    identity(b)
    return true
  end
  function api.destroy() buffer.destroy() end
  return api
end

function M.open()
  if _G.AtlanticaTimerTrial then
    _G.AtlanticaTimerTrial.form.bringToFront()
    return
  end
  local api = M.newCEAdapter()
  local trial = M.newTrial(api)
  local form = createForm(false)
  form.Caption = "Atlantica — prueba CE " .. M.version
  form.Width, form.Height = 620, 420
  form.Position = "poScreenCenter"
  local function label(text, y, height)
    local control = createLabel(form)
    control.Left, control.Top, control.Width, control.Height = 16, y, 580, height
    control.AutoSize, control.WordWrap, control.Caption = false, true, text
    return control
  end
  label("PID seleccionado en CE: " .. getOpenedProcessID() ..
    ". Bot detenido y Auto Battle apagado. Entra en combate antes de probar.", 12, 44)
  label("Cambia temporizadores de ese proceso, incluidas esperas de red. " ..
    "La prueba solicita 1× al terminar; no garantiza que el servidor acepte el ritmo.", 60, 44)
  local rates = createComboBox(form)
  rates.Left, rates.Top, rates.Width, rates.Style = 16, 112, 130, "csDropDownList"
  for _, rate in ipairs(M.rates) do rates.Items.add(tostring(rate) .. "×") end
  rates.ItemIndex = 0
  local start, stop = createButton(form), createButton(form)
  start.Left, start.Top, start.Width, start.Caption = 160, 110, 190, "Probar 10 segundos"
  stop.Left, stop.Top, stop.Width, stop.Caption = 365, 110, 220, "Restaurar 1× / parar"
  local status = label(trial.message, 152, 62)
  local log = createMemo(form)
  log.Left, log.Top, log.Width, log.Height = 16, 218, 580, 138
  log.ReadOnly, log.ScrollBars = true, "ssVertical"
  label("El factor informado por CE no confirma el efecto visual. " ..
    "No cierres CE a la fuerza durante la prueba. Puedes copiar este registro.", 364, 38)
  local function refresh()
    start.Enabled = trial.phase == "idle" and not trial.busy and trial.binding == nil
    rates.Enabled = start.Enabled
    status.Caption = trial.message
    if trial.phase == "active" then
      status.Caption = status.Caption .. " Restan " ..
        math.max(0, math.ceil((trial.deadline - api.now()) / 1000)) .. " s."
    end
    log.Lines.Text = table.concat(trial.history, "\r\n")
  end
  start.OnClick = function()
    local ok, err = pcall(trial.start, M.rates[rates.ItemIndex + 1])
    if not ok then trial.note(tostring(err)) end
    refresh()
  end
  stop.OnClick = function() trial.restore("Parada manual"); refresh() end
  local timer = createTimer(form, false)
  timer.Interval = 100
  timer.OnTimer = function() trial.tick(); refresh() end
  local nonModal, cleaned = false, false
  local function cleanup(destroyForm)
    if cleaned then return end
    cleaned = true
    timer.Enabled = false
    _G.AtlanticaTimerTrial = nil
    api.destroy()
    if destroyForm then form.destroy() end
  end
  form.OnClose = function()
    if not trial.close() then refresh(); return caNone end
    if nonModal then cleanup(false); return caFree end
    return caHide
  end
  _G.AtlanticaTimerTrial = {form = form, trial = trial}
  timer.Enabled = true
  -- Keep CE's normal process selection and speed controls unavailable while the
  -- experiment form is open. The game and the separate bot panel remain usable.
  local ok, err = pcall(function() form.showModal() end)
  timer.Enabled = false
  if not trial.close() then
    nonModal = true
    timer.Enabled = true
    refresh()
    form.show() -- keep restoration reachable if modal display itself failed
    return
  end
  cleanup(true)
  if not ok then error(err) end
end

if type(createForm) == "function" then M.open() end
return M
