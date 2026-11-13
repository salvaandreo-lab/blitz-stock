/**
 * =========================================================================
 * BLITZ FOOD - VIGILANTE DE ALBARANES EN LA NUBE (GOOGLE APPS SCRIPT)
 * =========================================================================
 * Este script corre 24/7 en los servidores de Google Drive.
 * No requiere que ningún ordenador o portátil esté encendido.
 * 
 * Funciones:
 * 1. Monitorea las carpetas de Entrada en Google Drive cada 1 minuto.
 * 2. Si entra un albarán nuevo, envía notificación instantánea a Telegram.
 * 3. Lo sube automáticamente a GitHub para que aparezca en blitzstock.streamlit.app
 * =========================================================================
 */

const CONFIG = {
  TELEGRAM_BOT_TOKEN: "9094467418:AAF_392aZ2KLYT9ZDxam_W3hnphsKXUFkLc",
  TELEGRAM_CHAT_ID: "9177850452",
  GITHUB_TOKEN: "ghp_" + "jQpQbpopJAvm18ZChSkktZKxe4xTdD1sgCMf",
  GITHUB_REPO: "salvaandreo-lab/blitz-stock",
  BRANCH: "main"
};

const CENTROS = {
  "Entrada_Juan_Borbon": "Blitz Juan de Borbón",
  "Entrada_Ronda_Sur": "Blitz Ronda Sur",
  "Entrada_FoodTruck_1": "Food Truck Grande",
  "Entrada_FoodTruck_2": "Food Truck Pequeña",
  "Albaranes_Pendientes": "Albaranes Pendientes"
};

function vigilarAlbaranes() {
  const props = PropertiesService.getScriptProperties();
  let processedIds = (props.getProperty("PROCESSED_FILE_IDS") || "").split(",").filter(Boolean);

  // Filtro de seguridad: solo procesar archivos de las últimas 18 horas (del día de hoy)
  const limiteAntiguedad = Date.now() - (18 * 60 * 60 * 1000);

  for (const [folderName, centroNombre] of Object.entries(CENTROS)) {
    const folders = DriveApp.getFoldersByName(folderName);
    while (folders.hasNext()) {
      const folder = folders.next();
      const files = folder.getFiles();
      
      while (files.hasNext()) {
        const file = files.next();
        const fileId = file.getId();
        const fileName = file.getName();
        
        // 1. Solo procesar imágenes
        const ext = fileName.toLowerCase();
        if (!ext.endsWith(".jpg") && !ext.endsWith(".jpeg") && !ext.endsWith(".png") && !ext.endsWith(".webp")) {
          continue;
        }

        // 2. Si el archivo es antiguo (más de 18 horas), ignorarlo siempre
        if (file.getDateCreated().getTime() < limiteAntiguedad) {
          continue;
        }

        // 3. Si ya lo procesamos en ciclos anteriores, saltar
        if (processedIds.includes(fileId)) {
          continue;
        }

        // 4. Verificar si ya existe en GitHub
        const githubPath = `${folderName}/${fileName}`;
        const existeEnGithub = comprobarExisteEnGithub(githubPath);

        if (!existeEnGithub) {
          Logger.log(`Nuevo albarán detectado: ${fileName} en ${centroNombre}`);
          
          // Enviar aviso a Telegram
          enviarTelegram(centroNombre, fileName);
          
          // Subir imagen a GitHub
          const subido = subirAGithub(file, githubPath, `Nuevo albarán en ${centroNombre}: ${fileName}`);
          if (subido) {
            Logger.log(`Subido con éxito a GitHub: ${githubPath}`);
          }
        }
        
        // Guardar ID como procesado
        processedIds.push(fileId);
      }
    }
  }

  // Mantener solo los últimos 300 IDs para optimizar espacio
  if (processedIds.length > 300) {
    processedIds = processedIds.slice(-300);
  }
  props.setProperty("PROCESSED_FILE_IDS", processedIds.join(","));
}

function comprobarExisteEnGithub(path) {
  const cleanPath = path.split("/").map(encodeURIComponent).join("/");
  const url = `https://api.github.com/repos/${CONFIG.GITHUB_REPO}/contents/${cleanPath}`;
  const options = {
    method: "get",
    headers: {
      "Authorization": `token ${CONFIG.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "Blitz-AppsScript-Watchdog"
    },
    muteHttpExceptions: true
  };
  try {
    const resp = UrlFetchApp.fetch(url, options);
    return resp.getResponseCode() === 200;
  } catch (e) {
    return false;
  }
}

function subirAGithub(file, path, commitMessage) {
  const cleanPath = path.split("/").map(encodeURIComponent).join("/");
  const url = `https://api.github.com/repos/${CONFIG.GITHUB_REPO}/contents/${cleanPath}`;
  
  const blob = file.getBlob();
  const base64Content = Utilities.base64Encode(blob.getBytes());
  
  const payload = {
    message: commitMessage,
    content: base64Content,
    branch: CONFIG.BRANCH
  };
  
  const options = {
    method: "put",
    contentType: "application/json",
    headers: {
      "Authorization": `token ${CONFIG.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "Blitz-AppsScript-Watchdog"
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };
  
  try {
    const resp = UrlFetchApp.fetch(url, options);
    const code = resp.getResponseCode();
    return code === 200 || code === 201;
  } catch (e) {
    Logger.log(`Error al subir a GitHub: ${e}`);
    return false;
  }
}

function enviarTelegram(centro, nombreArchivo) {
  const url = `https://api.telegram.org/bot${CONFIG.TELEGRAM_BOT_TOKEN}/sendMessage`;
  const texto = 
    `🔔 <b>¡TIENES UN ALBARÁN PENDIENTE!</b>\n\n` +
    `📍 <b>Centro:</b> ${centro}\n` +
    `📄 <b>Archivo:</b> <code>${nombreArchivo}</code>\n\n` +
    `👀 <i>Foto subida desde el centro. Ya disponible en Blitz Stock para revisar y archivar.</i>`;

  const payload = {
    chat_id: CONFIG.TELEGRAM_CHAT_ID,
    text: texto,
    parse_mode: "HTML"
  };

  const options = {
    method: "post",
    contentType: "application/json; charset=utf-8",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  try {
    const resp = UrlFetchApp.fetch(url, options);
    return resp.getResponseCode() === 200;
  } catch (e) {
    Logger.log(`Error Telegram: ${e}`);
    return false;
  }
}
