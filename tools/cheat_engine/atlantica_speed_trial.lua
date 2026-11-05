-- Atlantica: bounded manual Cheat Engine timer experiment.
-- Requires 64-bit Cheat Engine on Windows; the game itself is 32-bit.
-- Loading only opens the form. Automatic mode must be explicitly armed.
local M = {version = "0.18.0", rates = {1.25, 1.5, 2, 3, 4}, MAP = "__map__",
  GRAPHICS_OTHER = "__graphics_other__",
  NOT_READY = "__not_ready__",
  modeOrder = {"timed", "battle_end", "automatic"}, modes = {
    timed = {seconds = 10, label = "10 segundos"},
    battle_end = {seconds = 60, label = "Hasta salir del combate (máx. 60 s)"},
    automatic = {seconds = 60, label = "Automático en cada combate (máx. 60 s)"}
  }}

local function equalRate(a, b)
  return type(a) == "number" and math.abs(a - b) < 0.0001
end

-- The controller also runs against a fake adapter in the regression tests.
function M.newTrial(api)
  local t = {phase = "idle", message = "Sin cambios de velocidad.", binding = nil,
    ownsChange = false, history = {}, reportedRate = nil, busy = false, stopRequested = nil,
    historyRevision = 0, mode = "timed", duration = 10}

  function t.note(message)
    t.message = message
    t.history[#t.history + 1] = tostring(api.now()) .. " ms | " .. message
    t.historyRevision = t.historyRevision + 1
    if #t.history > 100 then table.remove(t.history, 1) end
  end

  function t.elapsed()
    if not t.startedAt then return 0 end
    return math.max(0, ((t.endedAt or api.now()) - t.startedAt) / 1000)
  end

  local function observation()
    local token, detail = api.observe(t.binding)
    t.lastObservation = detail
    return token
  end

  local function describeState()
    local d = api.lastObservation or t.lastObservation
    if not d then return end
    t.note("Última lectura: estado=" .. tostring(d.classification) ..
      ", escena=" .. tostring(d.scene_code) .. ", contextos=" ..
      tostring(d.context_a) .. "/" .. tostring(d.context_b) ..
      ", fase=" .. tostring(d.battle_phase) .. ", gráfico=" .. tostring(d.graphics_context_index))
  end

  function t.release()
    if t.binding then api.release(t.binding); t.binding = nil end
  end

  local function restoreNow(reason, cause)
    if not t.ownsChange then
      t.release()
      t.phase = "idle"
      t.note(reason .. "; no había cambio de temporizadores pendiente." ..
        (t.lastRestoration and " Última causa: " .. t.lastRestoration.reason .. "." or ""))
      return true
    end
    t.phase = "restoring"
    describeState()
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
    t.endedAt = api.now()
    t.lastRestoration = {cause = cause or "other", reason = reason,
      at = t.endedAt, seconds = t.elapsed(),
      pid = t.binding.pid, mode = t.mode, rate = t.rate, reported_rate = t.reportedRate,
      process_exited = result == "exited", observation = api.lastObservation or t.lastObservation}
    t.release()
    t.note(reason .. string.format(" (%.2f s)", t.elapsed()) ..
      (result == "exited" and "; la instancia terminó." or
      "; CE informa 1×. Comprueba el juego; esto no mide la animación."))
    return true
  end

  local function finishRestore(reason, cause)
    local ok, result = pcall(restoreNow, reason, cause)
    if not ok then
      t.phase = "restore_failed"
      t.note("Limpieza pendiente: " .. tostring(result))
      return false
    end
    return result
  end

  function t.restore(reason, cause)
    cause = cause or "manual"
    local receivedSeconds = t.startedAt and math.max(0, (api.now() - t.startedAt) / 1000) or 0
    t.note(reason .. string.format(" recibida a %.2f s; estado=%s.", receivedSeconds, t.phase))
    -- CE may pump GUI messages while injecting/loading symbols. A timer,
    -- close event, or Stop click must not start another nested speed request.
    if t.busy then
      if not t.stopRequested then t.stopRequested = {reason = reason, cause = cause} end
      return false
    end
    t.busy = true
    local result = finishRestore(reason, cause)
    t.stopRequested, t.busy = nil, false
    return result
  end

  function t.start(rate, mode)
    if t.busy then error("CE todavía está procesando la prueba.") end
    if t.binding or t.ownsChange then error("Termina o restaura la prueba anterior.") end
    local allowed = false
    for _, value in ipairs(M.rates) do if rate == value then allowed = true end end
    if not allowed then error("Elige una de las velocidades de prueba.") end
    mode = mode or "timed"
    if not M.modes[mode] or mode == "automatic" then error("Elige un modo de prueba válido.") end
    t.busy = true
    local ok, err = pcall(function()
      t.binding = api.bind()
      if not equalRate(api.reportedRate(), 1) then
        error("CE ya informa otra velocidad. Vuelve a 1× antes de probar.")
      end
      local battle = observation()
      if battle == M.MAP then error("Entra en un combate antes de iniciar la prueba.", 0) end
      if battle == M.GRAPHICS_OTHER then
        error("El contexto gráfico cambió. Espera un momento y vuelve a probar.", 0)
      end
      if battle == M.NOT_READY then error("El combate todavía no está listo. Espera el turno.", 0) end
      -- A rejected attempt must not erase the last completed trial or its cause.
      t.battle, t.mode, t.duration = battle, mode, M.modes[mode].seconds
      t.startedAt, t.endedAt, t.lastRestoration = nil, nil, nil
      t.rate, t.armedAt = rate, api.now()
      t.phase = "arming"
      t.note("PID " .. t.binding.pid .. ", creación " .. t.binding.created ..
        ": comprobando combate antes de aplicar " .. rate .. "×; modo=" .. mode .. ".")
    end)
    if not ok then
      finishRestore(tostring(err), "start_rejected")
      t.stopRequested, t.busy = nil, false
      return false
    end
    t.busy = false
    if t.stopRequested then
      local request = t.stopRequested
      t.stopRequested = nil
      t.restore(request.reason, request.cause)
      return false
    end
    return true
  end

  function t.tick()
    if t.busy then return end
    if t.phase ~= "arming" and t.phase ~= "active" then return end
    t.busy = true
    local ok, err = pcall(function()
      local current = observation()
      if t.stopRequested then
        finishRestore(t.stopRequested.reason, t.stopRequested.cause)
        return
      end
      if current == M.MAP then
        finishRestore("Salida del combate detectada", "battle_exit")
        return
      end
      if current == M.GRAPHICS_OTHER then
        finishRestore("Cambio del contexto gráfico; vuelta preventiva a 1×",
          "graphics_context_changed")
        return
      end
      if current == M.NOT_READY then
        finishRestore("El combate dejó de estar listo; vuelta preventiva a 1×", "battle_not_ready")
        return
      end
      if current ~= t.battle then error("El combate cambió.") end
      if t.phase == "arming" then
        if api.now() - t.armedAt < 200 then return end
        if not equalRate(api.reportedRate(), 1) then error("La velocidad de CE cambió.") end
        -- Retain ownership even if CE fails after partially installing its hooks.
        t.ownsChange = true
        t.startedAt = api.now()
        t.deadline = t.startedAt + t.duration * 1000
        t.phase = "applying"
        api.setRate(t.binding, t.rate)
        t.reportedRate = api.reportedRate()
        if not equalRate(t.reportedRate, t.rate) then error("CE no informa el factor solicitado.") end
        if t.stopRequested then
          finishRestore(t.stopRequested.reason, t.stopRequested.cause)
          return
        end
        if api.now() >= t.deadline then
          finishRestore("Plazo cumplido durante la carga de CE", "initialization_timeout")
          return
        end
        current = observation()
        if t.stopRequested then
          finishRestore(t.stopRequested.reason, t.stopRequested.cause)
          return
        end
        if current == M.MAP then
          finishRestore("Salida del combate detectada durante la aplicación", "battle_exit")
          return
        end
        if current == M.GRAPHICS_OTHER then
          finishRestore("Cambio del contexto gráfico durante la aplicación; vuelta preventiva a 1×",
            "graphics_context_changed")
          return
        end
        if current == M.NOT_READY then
          finishRestore("El combate cambió durante la aplicación; vuelta preventiva a 1×",
            "battle_not_ready")
          return
        end
        if current ~= t.battle then error("El combate cambió durante la aplicación.") end
        t.phase = "active"
        t.note("CE informa " .. t.rate .. "× en PID " .. t.binding.pid ..
          ". Ejecuta una magia manual; " .. M.modes[t.mode].label .. ".")
      elseif api.now() >= t.deadline then
        finishRestore(t.mode == "timed" and "Plazo de 10 s cumplido" or
          "Límite de 60 s cumplido sin confirmar salida del combate", "time_limit")
      elseif not equalRate(api.reportedRate(), t.rate) then
        error("La velocidad de CE cambió durante la prueba.")
      end
    end)
    if not ok then
      if t.stopRequested then finishRestore(t.stopRequested.reason, t.stopRequested.cause)
      else finishRestore(tostring(err), "observation_or_context_changed") end
    end
    if t.stopRequested and t.binding and t.phase ~= "restore_failed" then
      finishRestore(t.stopRequested.reason, t.stopRequested.cause)
    end
    t.stopRequested, t.busy = nil, false
  end

  function t.close()
    if not t.binding and not t.ownsChange and not t.busy then return true end
    return t.restore("Prueba cerrada", "window_closed")
  end

  return t
end

-- Hold a speed-only lease across encounters. Each encounter reuses the same
-- verified manual controller; ordinary attacks keep their independent Bot lease.
function M.newAutomatic(api)
  local t = M.newTrial(api)
  t.automatic, t.running, t.mode = true, false, "automatic"
  local child, forwarded, needMap, stopRequested

  local function forward()
    if not child then return end
    local first = math.max(1, #child.history - (child.historyRevision - (forwarded or 0)) + 1)
    for i = first, #child.history do
      t.history[#t.history + 1] = child.history[i]
      t.historyRevision = t.historyRevision + 1
      if #t.history > 100 then table.remove(t.history, 1) end
    end
    forwarded = child.historyRevision
    t.ownsChange = child.ownsChange
    t.startedAt, t.endedAt, t.duration = child.startedAt, child.endedAt, child.duration
    if child.lastRestoration then t.lastRestoration = child.lastRestoration end
    t.message = child.message
  end

  local function stopNow(reason)
    t.running = false
    if child and (child.binding or child.ownsChange or child.busy) then
      if not child.restore(reason, "manual") then
        forward()
        t.phase = "restore_failed"
        return false
      end
      forward()
    end
    t.release()
    child, stopRequested, t.ownsChange, t.phase = nil, nil, false, "idle"
    t.note("Automático desactivado. " .. reason .. ".")
    return true
  end

  local function guardedStop(reason)
    local ok, result = pcall(stopNow, reason)
    if not ok then
      t.running, t.phase = false, "restore_failed"
      t.note("Limpieza pendiente: " .. tostring(result) .. ". Pulsa Restaurar 1×.")
      return false
    end
    return result
  end

  function t.restore(reason)
    stopRequested = stopRequested or reason
    if t.busy then
      if child and child.busy then child.restore(reason, "manual") end
      return false
    end
    t.busy = true
    local result = guardedStop(stopRequested)
    t.busy = false
    return result
  end

  function t.start(rate)
    if t.busy or t.binding then error("Detén el automático anterior antes de activarlo.") end
    local allowed = false
    for _, value in ipairs(M.rates) do if value == rate then allowed = true end end
    if not allowed then error("Elige una de las velocidades de prueba.") end
    t.busy = true
    local ok, err = pcall(function()
      t.binding = api.bind("automatic")
      if not equalRate(api.reportedRate(), 1) then
        error("CE ya informa otra velocidad. Vuelve a 1× antes de activar el automático.")
      end
      local token, detail = api.observe(t.binding)
      t.actorIdentity = detail and detail.actor_identity
      t.rate, t.mode, t.duration = rate, "automatic", 60
      t.startedAt, t.endedAt, t.running = nil, nil, true
      needMap = token == M.GRAPHICS_OTHER
      child, forwarded = nil, 0
      t.phase = needMap and "waiting_map" or "waiting_battle"
      t.note("Automático activado para PID " .. t.binding.pid .. ", creación " ..
        t.binding.created .. "; factor=" .. rate .. "×; máximo 60 s por combate. " ..
        "Esperando un combate válido; puede usarse junto al bot de ataques.")
    end)
    if not ok then
      guardedStop(tostring(err))
      t.busy = false
      return false
    end
    if stopRequested and t.phase ~= "restore_failed" then guardedStop(stopRequested) end
    t.busy = false
    return t.running
  end

  function t.tick()
    if t.busy or not t.running then return end
    t.busy = true
    local ok, err = pcall(function()
      if child then
        child.tick()
        forward()
        if child.phase == "restore_failed" then
          t.running, t.phase = false, "restore_failed"
          return
        end
        if child.phase ~= "idle" then t.phase = child.phase; return end
        local result = child.lastRestoration
        if result and (result.process_exited or
          (result.cause ~= "battle_exit" and result.cause ~= "graphics_context_changed" and
           result.cause ~= "time_limit" and result.cause ~= "battle_not_ready")) then
          stopRequested = stopRequested or "Estado del cliente cambió; revisa el registro"
          return
        end
        -- A verified map boundary permits another encounter even when the
        -- client recycles the very same context pointer/token.
        local d = api.lastObservation
        needMap = not ((result and result.cause == "battle_exit") or
          (not result and d and (d.classification == "map" or d.classification == "not_ready")))
        child, forwarded = nil, 0
        t.phase = needMap and "waiting_map" or "waiting_battle"
        if not result and d and d.classification == "not_ready" then
          t.note("El turno aún no está listo; esperando a 1× antes de aplicar velocidad.")
        else
          t.note(needMap and
            "Automático sigue activado a 1×; espera el mapa antes de otro combate." or
            "Mapa confirmado a 1×; automático espera el siguiente combate.")
        end
        return
      end
      local token, detail = api.observe(t.binding)
      if t.actorIdentity and (not detail or detail.actor_identity ~= t.actorIdentity) then
        error("El personaje de la instancia cambió.")
      end
      if not equalRate(api.reportedRate(), 1) then
        error("CE informa una tasa ajena al automático; no se sobrescribió.")
      end
      if token == M.MAP then
        if needMap then t.note("Mapa confirmado a 1×; esperando el siguiente combate.") end
        needMap, t.phase = false, "waiting_battle"
        return
      end
      if token == M.NOT_READY then
        t.phase = needMap and "waiting_map" or "waiting_battle"
        return
      end
      if token == M.GRAPHICS_OTHER or needMap then
        needMap, t.phase = true, "waiting_map"
        return
      end
      -- The outer adapter owns the handles. A child may restore its rate, but
      -- must not release this lease while the automatic controller is armed.
      local function observeOwned(plan)
        local value, frame = api.observe(plan)
        if t.actorIdentity and (not frame or frame.actor_identity ~= t.actorIdentity) then
          error("El personaje cambió antes de aplicar velocidad.")
        end
        return value, frame
      end
      local shared = setmetatable({bind = function() return t.binding end,
        release = function() end, observe = observeOwned}, {__index = api})
      child, forwarded = M.newTrial(shared), 0
      needMap = true
      local started = child.start(t.rate, "battle_end")
      forward()
      if not started then
        if child.phase == "restore_failed" then t.running, t.phase = false, "restore_failed"; return end
        if not equalRate(api.reportedRate(), 1) then error("La tasa de CE cambió.") end
        local d = api.lastObservation
        if not d or (d.classification ~= "not_ready" and d.classification ~= "map" and
                     d.classification ~= "graphics_other") then
          stopRequested = stopRequested or "No se pudo verificar el inicio de velocidad"
          return
        end
        needMap = not (d and (d.classification == "not_ready" or d.classification == "map"))
        child, t.phase = nil, needMap and "waiting_map" or "waiting_battle"
        t.note(needMap and "Inicio de velocidad rechazado; esperando el mapa antes de otro combate." or
          "Esperando a que el combate publique un turno válido antes de aplicar velocidad.")
        return
      end
      t.phase = "arming"
    end)
    if not ok then stopRequested = stopRequested or tostring(err) end
    if stopRequested and t.phase ~= "restore_failed" then guardedStop(stopRequested) end
    t.busy = false
  end

  function t.close()
    if not t.binding and not t.busy then return true end
    return t.restore("Ventana cerrada")
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
    if b.speed_mutex then
      win("ReleaseMutex", b.speed_mutex); win("CloseHandle", b.speed_mutex); b.speed_mutex = nil
    end
    if b.handle then win("CloseHandle", b.handle); b.handle = nil end
  end
  function api.bind(leaseMode)
    assert(leaseMode == nil or leaseMode == "automatic", "Modo de reserva no reconocido.")
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
      local function reserve(kind)
        local mutex = win("CreateMutexW", 0, 0,
          {type = 4, value = "Local\\AtlanticaPanel." .. kind .. "." .. b.pid})
        assert(mutex ~= 0, "No se pudo reservar el PID.")
        local result = win("WaitForSingleObject", mutex, 0)
        if result ~= 0 and result ~= 0x80 then
          win("CloseHandle", mutex)
          error(kind == "Speed" and "Otro controlador de velocidad ya usa ese PID." or
            "Detén el bot antes de iniciar una prueba manual de velocidad.")
        end
        return mutex
      end
      b.speed_mutex = reserve("Speed")
      if leaseMode ~= "automatic" then b.mutex = reserve("Bot") end
      identity(b)
    end)
    if not ok then api.release(b); error(err) end
    return b
  end
  function api.observe(b)
    identity(b)
    assert(not fileExists(b.marker), "Desactiva HuntingMode.txt antes de probar.")
    local function snapshot()
      local d = {classification = "unknown"}
      api.lastObservation = d
      local owner = pointer(0x04a9290c)
      d.scene_code = read32(owner + 0xb98)
      assert(d.scene_code == 2, "Escena no disponible.")
      local auto = readBytes(owner + 0x16394, 1)
      local hunting = readBytes(0x04e52c5a, 1)
      assert(auto == 0 and hunting == 0, "Apaga Auto Battle y la caza nativa.")
      local world = pointer(owner + 0x828)
      local actor = pointer(world + 0x2c)
      assert(read32(actor + 0x200) == 1 and read32(actor + 0x2c) == world,
        "El personaje local cambió.")
      local index = read32(actor + 0x318)
      local contextB = read32(actor + 0x254)
      d.context_a = index == 0xffffffff and -1 or index
      d.context_b = contextB == 0xffffffff and -1 or contextB
      d.graphics_context_index = read32(0x1539ce18)
      assert(d.graphics_context_index == 0 or d.graphics_context_index == 1,
        "El contexto gráfico no tiene un valor reconocido.")
      local key = {owner, world, actor, index, contextB, d.graphics_context_index,
        read32(actor + 0x204), read32(actor + 0x208), read32(actor + 0x20c)}
      d.actor_identity = table.concat({key[7], key[8], key[9]}, ":")
      -- The labelled map/battle/map captures on this exact build verified these
      -- local context fields. Do not treat read errors or an arbitrary new scene
      -- as a successful return to the map.
      if index == 0xffffffff and contextB == 0xffffffff then
        d.classification = "map"
        return {token = M.MAP, signature = table.concat(key, ":"), detail = d}
      end
      assert(index < 128 and contextB == 0xffffffff,
        "La prueba requiere un combate normal activo.")
      local manager = pointer(owner + 0x91c)
      d.battle_phase = read32(manager + 0x234c)
      assert(read32(manager) == 0x042d8aa4, "El gestor no coincide con el cliente verificado.")
      key[#key + 1], key[#key + 2] = manager, d.battle_phase
      local function notReady()
        d.classification = "not_ready"
        return {token = M.NOT_READY, signature = table.concat(key, ":"), detail = d}
      end
      if d.battle_phase ~= 3 then return notReady() end
      local context = read32(manager + 8 + index * 4)
      key[#key + 1] = context
      if context == 0 then return notReady() end
      assert(context >= 0x10000 and context <= 0xffff0000, "Puntero transitorio del combate.")
      d.turn_number = read32(context + 0x6c74)
      if d.turn_number == 0xffffffff then return notReady() end
      if d.graphics_context_index == 0 then
        -- The user's two captures retained local context 0/-1 and phase 3
        -- while selecting graphics context 0. Restore promptly, but do not
        -- confuse this value alone with a verified departure from battle.
        d.classification = "graphics_other"
        return {token = M.GRAPHICS_OTHER, signature = table.concat(key, ":"), detail = d}
      end
      d.classification = "battle"
      local token = table.concat(key, ":")
      return {token = token, signature = token, detail = d}
    end
    local before, after = snapshot(), snapshot()
    if before.signature ~= after.signature then
      api.lastObservation.classification = "unknown"
      error("Los objetos del combate cambiaron durante la lectura.")
    end
    identity(b)
    return after.token, after.detail
  end
  function api.setRate(b, rate)
    identity(b)
    if rate ~= 1 then
      local token = api.observe(b)
      assert(token ~= M.MAP, "La instancia ya volvió al mapa; no se aplicó velocidad.")
      assert(token ~= M.GRAPHICS_OTHER, "El contexto gráfico cambió; no se aplicó velocidad.")
      assert(token ~= M.NOT_READY, "El combate todavía no está listo; no se aplicó velocidad.")
    end
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
  form.Width, form.Height = 700, 560
  form.Position = "poScreenCenter"
  local function label(text, y, height)
    local control = createLabel(form)
    control.Left, control.Top, control.Width, control.Height = 16, y, 660, height
    control.AutoSize, control.WordWrap, control.Caption = false, true, text
    return control
  end
  label("PID seleccionado en CE: " .. getOpenedProcessID() ..
    ". Auto Battle apagado. Pruebas manuales: bot detenido. " ..
    "Automático: puede funcionar junto al bot de ataques.", 12, 44)
  label("Cambia temporizadores de ese proceso, incluidas esperas de red. " ..
    "La prueba solicita 1× al terminar; no garantiza que el servidor acepte el ritmo.", 60, 44)
  local rates, modes = createComboBox(form), createComboBox(form)
  rates.Name, modes.Name = "TrialRate", "TrialMode"
  rates.Left, rates.Top, rates.Width, rates.Style = 16, 112, 100, "csDropDownList"
  for _, rate in ipairs(M.rates) do rates.Items.add(tostring(rate) .. "×") end
  rates.ItemIndex = 0
  modes.Left, modes.Top, modes.Width, modes.Style = 130, 112, 400, "csDropDownList"
  for _, mode in ipairs(M.modeOrder) do modes.Items.add(M.modes[mode].label) end
  modes.ItemIndex = 0
  local start, stop = createButton(form), createButton(form)
  start.Left, start.Top, start.Width, start.Caption = 16, 150, 310, "Probar 10 segundos"
  stop.Left, stop.Top, stop.Width, stop.Caption = 342, 150, 310, "Restaurar 1× / parar"
  modes.OnChange = function()
    start.Caption = ({"Probar 10 segundos", "Probar hasta salir del combate",
      "Activar en cada combate"})[modes.ItemIndex + 1]
  end
  local status = label(trial.message, 193, 64)
  local clock = label("Sin prueba activa.", 260, 26)
  local log = createMemo(form)
  log.Left, log.Top, log.Width, log.Height = 16, 294, 660, 128
  log.ReadOnly, log.ScrollBars = true, "ssVertical"
  local copy = createButton(form)
  copy.Left, copy.Top, copy.Width, copy.Caption = 16, 432, 220, "Copiar registro"
  copy.OnClick = function()
    writeToClipboard("Atlantica — prueba CE " .. M.version .. "\r\n" ..
      table.concat(trial.history, "\r\n"))
  end
  label("El factor informado por CE no confirma el efecto visual. " ..
    "No cierres CE a la fuerza durante la prueba.", 472, 36)
  local logRevision = -1
  local phases = {idle = "sin prueba activa", arming = "comprobando", applying = "aplicando",
    active = "activa", restoring = "restaurando 1×", restore_failed = "restauración pendiente",
    waiting_battle = "esperando combate", waiting_map = "esperando el mapa"}
  local function refresh()
    start.Enabled = trial.phase == "idle" and not trial.busy and trial.binding == nil
    rates.Enabled = start.Enabled
    modes.Enabled = start.Enabled
    status.Caption = trial.message
    if trial.startedAt then
      local counting = trial.phase == "active" or trial.phase == "arming" or trial.phase == "applying"
      local prefix = counting and "Transcurrido: " or "Última prueba: "
      clock.Caption = prefix .. string.format("%.1f s / límite %d s. Estado: %s.",
        trial.elapsed(), trial.duration, phases[trial.phase] or trial.phase)
    else
      clock.Caption = "Estado: " .. (phases[trial.phase] or trial.phase) .. "."
    end
    -- Replacing Lines.Text on every timer tick used to discard the selection
    -- while the user tried Ctrl+A/C. Only update when a record changes.
    if logRevision ~= trial.historyRevision then
      log.Lines.Text = table.concat(trial.history, "\r\n")
      logRevision = trial.historyRevision
    end
  end
  start.OnClick = function()
    local mode = M.modeOrder[modes.ItemIndex + 1]
    local automatic = mode == "automatic"
    if not not trial.automatic ~= automatic then
      local nextTrial = automatic and M.newAutomatic(api) or M.newTrial(api)
      for _, name in ipairs({"history", "historyRevision", "lastRestoration",
        "startedAt", "endedAt", "duration"}) do nextTrial[name] = trial[name] end
      trial = nextTrial
      _G.AtlanticaTimerTrial.trial = trial
    end
    local ok, err = pcall(trial.start, M.rates[rates.ItemIndex + 1],
      mode)
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
