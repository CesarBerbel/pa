/**
 * Ponte entre o Django e o WhatsApp, através do Baileys.
 *
 * O Baileys é uma biblioteca Node e o resto da aplicação é Django. Em vez de
 * tentar juntar os dois no mesmo processo, este serviço mantém a ligação ao
 * WhatsApp viva e expõe três coisas ao Django por HTTP: o QR code para ligar,
 * o estado da ligação e o envio de mensagens.
 *
 * A ligação é uma sessão, não uma credencial: emparelha-se uma vez lendo o QR
 * com o telemóvel e fica válida até alguém a terminar. Por isso as chaves são
 * gravadas em disco (AUTH_DIR, um volume do Docker) — se ficassem em memória,
 * cada reinício obrigaria a ler o QR outra vez.
 */

const fs = require('fs')
const path = require('path')

const express = require('express')
const pino = require('pino')
const qrcode = require('qrcode')

const {
  default: makeWASocket,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  useMultiFileAuthState,
} = require('@whiskeysockets/baileys')

const PORT = parseInt(process.env.PORT || '3000', 10)
const AUTH_DIR = process.env.AUTH_DIR || '/data/auth'
const API_TOKEN = (process.env.BAILEYS_API_TOKEN || '').trim()
const LOG_LEVEL = process.env.LOG_LEVEL || 'info'

// Nome que aparece no telemóvel, em "Dispositivos ligados".
const DEVICE_NAME = process.env.BAILEYS_DEVICE_NAME || 'Priscila Arantes PA'

const logger = pino({ level: LOG_LEVEL })

// O Baileys é falador ao nível de debug e o que interessa aqui são os eventos
// de ligação, que tratamos à mão.
const baileysLogger = pino({ level: 'error' })

const STATE_STARTING = 'starting'
const STATE_WAITING_QR = 'waiting_qr'
const STATE_CONNECTING = 'connecting'
const STATE_CONNECTED = 'connected'
const STATE_DISCONNECTED = 'disconnected'
const STATE_LOGGED_OUT = 'logged_out'

/** Tudo o que o Django precisa de saber sobre a ligação. */
const status = {
  state: STATE_STARTING,
  qr: '', // data URL do PNG, vazio quando não há QR pendente
  qrExpiresAt: null,
  me: null, // { id, name } do número ligado
  lastError: '',
  connectedAt: null,
  updatedAt: new Date().toISOString(),
}

let sock = null

// Duas ligações em simultâneo invalidam-se uma à outra e a sessão entra num
// ciclo de reconexões. Este par de variáveis garante um arranque de cada vez.
let starting = false
let reconnectTimer = null

// Um socket fechado continua a emitir durante algum tempo. Sem esta marca, o
// `creds.update` de uma ligação já morta voltava a gravar em disco as
// credenciais revogadas que o resetAuth tinha acabado de apagar, e a ligação
// seguinte arrancava outra vez com elas.
let geracao = 0

/** Fecha um socket e cala-o, para não interferir com o que vier a seguir. */
function descartarSocket(anterior) {
  if (!anterior) {
    return
  }

  try {
    anterior.ev.removeAllListeners()
  } catch (erro) {
    logger.warn({ erro: erro.message }, 'Falha a remover listeners')
  }

  try {
    anterior.end(undefined)
  } catch (erro) {
    logger.warn({ erro: erro.message }, 'Falha a fechar a ligação anterior')
  }
}

function setStatus(patch) {
  Object.assign(status, patch, { updatedAt: new Date().toISOString() })
}

function clearReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

// Fechos seguidos sem nada pelo meio. Serve para ir afastando as tentativas:
// insistir de segundo a segundo não recupera a ligação e arrisca que o
// WhatsApp bloqueie o número por excesso de tentativas.
let falhasSeguidas = 0

function atrasoComRecuo(base) {
  return Math.min(base * 2 ** Math.min(falhasSeguidas, 5), 60000)
}

function scheduleReconnect(delayMs = 5000) {
  clearReconnect()

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    start().catch((erro) => {
      logger.error({ erro: erro.message }, 'Falha a reconectar')
      setStatus({ state: STATE_DISCONNECTED, lastError: erro.message })
      scheduleReconnect(15000)
    })
  }, delayMs)
}

/**
 * Abre a ligação ao WhatsApp e mantém o estado atualizado.
 *
 * Não devolve uma promessa que espera pela ligação: o emparelhamento pode
 * demorar o tempo que a pessoa levar a ler o QR, e quem chama isto só precisa
 * de saber que o processo arrancou.
 */
async function start() {
  if (starting) {
    return
  }

  starting = true

  // Tudo o que este arranque criar fica marcado com este número. Se entretanto
  // arrancar outra ligação, os eventos desta deixam de ter efeito.
  geracao += 1
  const minhaGeracao = geracao

  descartarSocket(sock)
  sock = null

  try {
    fs.mkdirSync(AUTH_DIR, { recursive: true })

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
    const { version } = await fetchLatestBaileysVersion()

    logger.info({ version }, 'A abrir ligação ao WhatsApp')

    setStatus({ state: STATE_CONNECTING, lastError: '' })

    sock = makeWASocket({
      version,
      logger: baileysLogger,
      auth: {
        creds: state.creds,
        // A cache evita reler as chaves do disco a cada mensagem.
        keys: makeCacheableSignalKeyStore(state.keys, baileysLogger),
      },
      browser: [DEVICE_NAME, 'Chrome', '1.0.0'],
      // O WhatsApp mostraria a clínica como "online" sempre que o container
      // estivesse de pé, o que não corresponde a ninguém estar a atender.
      markOnlineOnConnect: false,
      syncFullHistory: false,
    })

    sock.ev.on('creds.update', async () => {
      if (minhaGeracao !== geracao) {
        return
      }

      await saveCreds()
    })

    sock.ev.on('connection.update', async (update) => {
      if (minhaGeracao !== geracao) {
        return
      }

      const { connection, lastDisconnect, qr } = update

      if (qr) {
        try {
          const dataUrl = await qrcode.toDataURL(qr, { margin: 1, width: 320 })

          setStatus({
            state: STATE_WAITING_QR,
            qr: dataUrl,
            // O WhatsApp roda o código a cada 20 segundos; o ecrã usa isto
            // para saber que o que está a mostrar já não serve.
            qrExpiresAt: new Date(Date.now() + 20000).toISOString(),
          })

          // Chegou um QR: a ligação ao WhatsApp está boa, só falta alguém ler.
          falhasSeguidas = 0

          logger.info('QR code novo à espera de leitura')
        } catch (erro) {
          logger.error({ erro: erro.message }, 'Falha a gerar o QR code')
        }
      }

      if (connection === 'open') {
        clearReconnect()

        falhasSeguidas = 0

        setStatus({
          state: STATE_CONNECTED,
          qr: '',
          qrExpiresAt: null,
          lastError: '',
          connectedAt: new Date().toISOString(),
          me: sock.user ? { id: sock.user.id, name: sock.user.name || '' } : null,
        })

        logger.info({ me: status.me }, 'Ligado ao WhatsApp')
      }

      if (connection === 'close') {
        const codigo = lastDisconnect?.error?.output?.statusCode
        const motivo = lastDisconnect?.error?.message || ''

        // 401 é a sessão terminada no telemóvel. Reconectar com credenciais
        // revogadas nunca resulta: é preciso ler um QR novo.
        const terminada = codigo === DisconnectReason.loggedOut

        setStatus({
          state: terminada ? STATE_LOGGED_OUT : STATE_DISCONNECTED,
          qr: '',
          qrExpiresAt: null,
          me: null,
          connectedAt: null,
          lastError: motivo,
        })

        logger.warn({ codigo, motivo }, 'Ligação fechada')

        starting = false

        // Calar esta ligação antes de mexer no disco: um `creds.update`
        // atrasado gravaria de novo o que o resetAuth está prestes a apagar.
        geracao += 1
        descartarSocket(sock)
        sock = null

        if (terminada) {
          await resetAuth()
        }

        falhasSeguidas += 1

        // Mesmo depois de terminada: apagadas as credenciais, o arranque
        // seguinte gera o QR novo sem ninguém ter de carregar em nada.
        scheduleReconnect(atrasoComRecuo(terminada ? 1000 : 5000))

        return
      }
    })
  } finally {
    // O arranque acaba quando o socket está criado; ligar-se ao WhatsApp pode
    // demorar o tempo que a pessoa levar a ler o QR e não é esperado aqui.
    starting = false
  }
}

/**
 * Apaga as credenciais gravadas, para o próximo arranque pedir um QR novo.
 *
 * Apaga o *conteúdo* de AUTH_DIR e não o próprio AUTH_DIR: em produção é o
 * ponto de montagem de um volume do Docker, e o rmdir de um mountpoint dá
 * sempre EBUSY. Pior, o rmSync recursivo aborta nesse erro sem ter apagado
 * ficheiro nenhum — as credenciais revogadas sobreviviam e o serviço ficava
 * a tentar ligar-se com elas, em ciclo, sem nunca chegar a mostrar um QR.
 */
async function resetAuth() {
  let apagados = 0

  try {
    fs.mkdirSync(AUTH_DIR, { recursive: true })

    for (const nome of fs.readdirSync(AUTH_DIR)) {
      try {
        fs.rmSync(path.join(AUTH_DIR, nome), { recursive: true, force: true })
        apagados += 1
      } catch (erro) {
        // Um ficheiro preso não pode impedir os outros de desaparecerem: o que
        // sobrar de uma sessão revogada só serve para a bloquear outra vez.
        logger.error({ erro: erro.message, nome }, 'Falha a apagar credencial')
      }
    }

    logger.info({ apagados }, 'Credenciais apagadas')
  } catch (erro) {
    logger.error({ erro: erro.message }, 'Falha a apagar as credenciais')
  }
}

/**
 * Passa um número para o JID que o WhatsApp usa.
 *
 * Aceita o que vier — +351 912 345 678, 351912345678, whatsapp:+351... — e
 * devolve vazio quando não sobra um número utilizável, para quem chama poder
 * responder com um erro em vez de enviar para lado nenhum.
 */
function toJid(raw) {
  let valor = String(raw || '').trim()

  if (valor.startsWith('whatsapp:')) {
    valor = valor.slice('whatsapp:'.length)
  }

  if (valor.includes('@')) {
    return valor
  }

  const digitos = valor.replace(/\D/g, '')

  if (digitos.length < 9) {
    return ''
  }

  return `${digitos}@s.whatsapp.net`
}

const app = express()

app.use(express.json({ limit: '256kb' }))

/** O serviço não está exposto à internet, mas o token evita que qualquer
 *  container da mesma rede possa enviar mensagens em nome da clínica. */
function requireToken(req, res, next) {
  if (!API_TOKEN) {
    return res.status(500).json({
      error: 'BAILEYS_API_TOKEN não está definido no serviço.',
    })
  }

  const recebido = (req.get('X-Auth-Token') || '').trim()

  if (recebido !== API_TOKEN) {
    return res.status(401).json({ error: 'Token inválido.' })
  }

  return next()
}

// Sem token: é o que o Docker usa para saber se o container está de pé, e
// nessa altura ainda não há ligação nenhuma ao WhatsApp.
app.get('/health', (req, res) => {
  res.json({ ok: true, state: status.state })
})

app.get('/status', requireToken, (req, res) => {
  res.json(status)
})

app.post('/send', requireToken, async (req, res) => {
  const { to, text } = req.body || {}

  if (!text || !String(text).trim()) {
    return res.status(400).json({ error: 'Mensagem vazia.' })
  }

  const jid = toJid(to)

  if (!jid) {
    return res.status(400).json({ error: `Número inválido: ${to}` })
  }

  if (status.state !== STATE_CONNECTED || !sock) {
    return res.status(409).json({
      error: 'O WhatsApp não está ligado. Leia o QR code para ligar.',
      state: status.state,
    })
  }

  try {
    // Enviar para um número sem WhatsApp não dá erro nenhum: a mensagem é
    // aceite e desaparece. Confirmar antes é a única forma de o saber.
    const [encontrado] = await sock.onWhatsApp(jid)

    if (!encontrado || !encontrado.exists) {
      return res.status(404).json({
        error: `O número ${to} não tem WhatsApp.`,
      })
    }

    const enviada = await sock.sendMessage(encontrado.jid, { text: String(text) })

    return res.json({
      success: true,
      id: enviada?.key?.id || '',
      to: encontrado.jid,
    })
  } catch (erro) {
    logger.error({ erro: erro.message, jid }, 'Falha no envio')

    return res.status(502).json({ error: erro.message })
  }
})

app.post('/logout', requireToken, async (req, res) => {
  clearReconnect()

  try {
    if (sock) {
      await sock.logout()
    }
  } catch (erro) {
    // Se a sessão já não existe do lado do WhatsApp, o logout falha e não há
    // nada a fazer sobre isso: o que interessa é apagar o que está cá.
    logger.warn({ erro: erro.message }, 'Logout devolveu erro')
  }

  geracao += 1
  descartarSocket(sock)
  sock = null
  starting = false
  falhasSeguidas = 0

  await resetAuth()

  setStatus({
    state: STATE_STARTING,
    qr: '',
    qrExpiresAt: null,
    me: null,
    connectedAt: null,
    lastError: '',
  })

  scheduleReconnect(1000)

  return res.json({ success: true })
})

app.post('/restart', requireToken, async (req, res) => {
  clearReconnect()

  geracao += 1
  descartarSocket(sock)
  sock = null
  starting = false
  falhasSeguidas = 0

  setStatus({ state: STATE_STARTING, qr: '', qrExpiresAt: null, lastError: '' })

  scheduleReconnect(500)

  return res.json({ success: true })
})

app.listen(PORT, '0.0.0.0', () => {
  logger.info({ port: PORT, authDir: AUTH_DIR }, 'Serviço Baileys a ouvir')

  start().catch((erro) => {
    logger.error({ erro: erro.message }, 'Falha no arranque')
    setStatus({ state: STATE_DISCONNECTED, lastError: erro.message })
    scheduleReconnect(10000)
  })
})

// Sem isto, uma falha não tratada dentro do Baileys derrubava o processo e
// levava a ligação com ela.
process.on('unhandledRejection', (erro) => {
  logger.error({ erro: erro?.message || String(erro) }, 'Promessa rejeitada')
})
